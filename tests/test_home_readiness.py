import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('home_readiness',Path(__file__).resolve().parents[1]/'home-server/deploy.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReadinessTests(unittest.TestCase):
    def test_direct_runner_commands(self):
        for executable in ('python', 'python3'):
            for flags in ([], ['-u']):
                self.assertTrue(module.runner_command_valid([executable, *flags, '-m', 'home_server.runner']))
        for argv in (None, [], ['sh', '-c', 'python -m home_server.runner'],
                     ['python', '-m', 'another.module'],
                     ['python', '-m', 'home_server.runner', 'extra']):
            self.assertFalse(module.runner_command_valid(argv))

    def update_fixture(self, directory, native):
        home=Path(directory)
        state=home/'apps/funzug-automation/scheduler/native-state'
        state.mkdir(parents=True)
        (state/'native-worker.json').write_text(json.dumps(native))
        (state/'execution-owner.json').write_text(json.dumps({'owner':'home'}))
        return home

    def test_home_repair_preserves_cooldown_and_retains_old_container(self):
        with tempfile.TemporaryDirectory() as directory:
            native={'browser_retry_after':module.time.time()+3600,'browser_block_reason':'meta_planner_unavailable','items':{'due':{'status':'scheduled','error':'native_worker_check_failed'}}}
            home=self.update_fixture(directory,native)
            calls=[]
            def command(args,*unused):
                calls.append(args)
                if args[:2]==['docker','inspect']:
                    if args[2]=='funzug-home-worker':return json.dumps([{'State':{'Running':False}}])
                    return json.dumps([{'State':{'Running':False}},{'State':{'Running':False}}])
                if args[0]=='git':return 'a'*40
                return ''
            with patch.object(module.Path,'home',return_value=home),patch.object(module,'command',side_effect=command),patch.object(module,'compose') as compose,patch.object(module,'private_write') as write:
                result=module.update_home()
            self.assertEqual(result['result'],'home_update_started')
            self.assertEqual(json.loads((home/'apps/funzug-automation/scheduler/native-state/native-worker.json').read_text()),native)
            self.assertFalse(any(args[:2] in (['docker','rm'],['docker','restart']) for args in calls))
            self.assertTrue(any(args[:2]==['docker','rename'] for args in calls))
            compose.assert_any_call('up','-d','--no-build',project='funzug-home-'+'a'*12)
            self.assertEqual(write.call_args.args[0],module.BASE/'home-update.json')

    def test_home_update_preserves_actual_restriction_after_timer_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            home=self.update_fixture(directory,{'browser_retry_after':0,'browser_block_reason':'meta_temporarily_blocked'})
            with patch.object(module.Path,'home',return_value=home),patch.object(module,'command') as command:
                self.assertEqual(module.update_home()['failed_checks'],['browser_restricted'])
            command.assert_not_called()

    def test_home_update_failed_tests_leave_current_worker_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            home=self.update_fixture(directory,{})
            calls=[]
            def command(args,*unused):
                calls.append(args)
                if args[:2]==['docker','inspect']:
                    return json.dumps([{'State':{'Running':False}},{'State':{'Running':False}}])
                if args[0]=='git':return 'a'*40
                raise RuntimeError('isolated test failed')
            with patch.object(module.Path,'home',return_value=home),patch.object(module,'command',side_effect=command),patch.object(module,'compose'):
                with self.assertRaisesRegex(RuntimeError,'isolated test failed'):module.update_home()
            self.assertFalse(any(args[:2] in (['docker','stop'],['docker','rename'],['docker','start']) for args in calls))

    def test_missing_credential_blocks_cutover(self):
        result=module.assess({'items':[]},{'rows':[], 'missing_secret_names':['FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL'],
                                          'credential_valid':False,'renewal_storage_writable':False})
        self.assertIn('local_renewal_credential_missing',result)
        self.assertIn('renewal_output_store_not_provisioned',result)
        self.assertTrue(result)

    def test_comparison_detects_slot_mismatch(self):
        queue={'items':[{'id':'fixture','scheduled_at':'2026-10-25T12:00:00+05:30'}]}
        probe={'rows':[{'id':'fixture','slot':'2026-10-25T13:00:00+05:30'}],
               'missing_secret_names':[],'credential_valid':True,'renewal_storage_writable':True}
        self.assertIn('owner_slot_mismatch',module.assess(queue,probe))

    def test_probe_contains_no_mutation_calls(self):
        self.assertNotIn("'POST'",module.PROBE)
        self.assertNotIn('refresh_bundle(',module.PROBE)
        self.assertNotIn('submit(',module.PROBE)


if __name__=='__main__':
    unittest.main()
