import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('home_readiness',Path(__file__).resolve().parents[1]/'home-server/deploy.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReadinessTests(unittest.TestCase):
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
