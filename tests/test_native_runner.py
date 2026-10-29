import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock

from scheduler.native_runner import candidates,publication_candidates,read_api,tick,error_backoff_seconds,safe_error_diagnostics,defer_browser,recently_verified
from scheduler.native_worker import IST,NativeFailure


class NativeRunnerTests(unittest.TestCase):
    def test_unfinished_handoffs_precede_old_schedule_reverification(self):
        slot=(dt.datetime.now(IST)+dt.timedelta(days=2)).isoformat()
        rows=[{'externalId':name,'status':'approved','publicationAuthorized':True,
               'scheduleTimezone':'Asia/Kolkata','proposedSchedule':slot,
               'nativeHandoff':{'state':phase}}
              for name,phase in [('fresh',None),('old-a','scheduled'),('old-b','scheduled'),
                                 ('old-c','scheduled'),('pending','reserved')]]
        seen=[]
        def read(config,route,query):
            return {'drafts':rows} if route=='drafts' else {'externalId':query['externalId']}
        def advance_item(packet,*args):
            seen.append(packet['externalId'])
            return 'reserved'
        with patch('scheduler.native_runner.read_api',side_effect=read),patch('scheduler.native_runner.auth',return_value='fixture'),patch('scheduler.native_runner.write_state'),patch('scheduler.native_runner.CheckpointDispatcher'),patch('scheduler.meta_browser.MetaBrowser'),patch('scheduler.native_runner.advance',side_effect=advance_item):
            tick({},Path('nonexistent-priority-fixture.json'),None,True)
        self.assertEqual(seen[0],'pending')
        self.assertEqual(len(seen),3)

    def test_pending_checkpoint_stops_batch_before_another_dispatch(self):
        slot=(dt.datetime.now(IST)+dt.timedelta(days=1)).isoformat()
        rows=[{'externalId':name,'status':'approved','publicationAuthorized':True,
               'scheduleTimezone':'Asia/Kolkata','proposedSchedule':slot}
              for name in ('first','second')]
        with patch('scheduler.native_runner.read_api',side_effect=[{'drafts':rows},{}]) as read,patch('scheduler.native_runner.auth',return_value='fixture'),patch('scheduler.native_runner.write_state'),patch('scheduler.native_runner.CheckpointDispatcher'),patch('scheduler.meta_browser.MetaBrowser'),patch('scheduler.native_runner.advance',side_effect=NativeFailure('checkpoint_pending_reconciliation')) as advance:
            tick({},Path('nonexistent-serialized-checkpoint-state.json'),None,True)
        self.assertEqual(read.call_count,2)
        advance.assert_called_once()

    def test_browser_block_survives_restart_without_browser_or_workflow_activity(self):
        state = {'items':{},'enabled':True}
        defer_browser(state, 'meta_temporarily_blocked', 1000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            path.write_text(json.dumps(state))
            with patch('scheduler.native_runner.time.time',return_value=1100),patch('scheduler.native_runner.read_api',return_value={'drafts':[]}),patch('scheduler.native_runner.auth') as auth,patch('scheduler.native_runner.write_state') as save,patch('scheduler.meta_browser.MetaBrowser') as browser:
                tick({},path,None,True)
        auth.assert_not_called()
        browser.assert_not_called()
        self.assertEqual(save.call_args.args[1]['browser_block_reason'],'meta_temporarily_blocked')
        self.assertEqual(save.call_args.args[1]['browser_retry_after'],4600)

    def test_verified_schedule_cache_is_invalidated_by_reschedule_or_content_change(self):
        row = {'contentHash':'reviewed','proposedSchedule':'2026-10-20T16:30:00+05:30'}
        local = {'status':'scheduled','last_verified_at':10000,
                 'binding':{'content_hash':'reviewed','scheduled_at':row['proposedSchedule']}}
        self.assertTrue(recently_verified(row,local,11000))
        self.assertFalse(recently_verified({**row,'contentHash':'changed'},local,11000))
        self.assertFalse(recently_verified({**row,'proposedSchedule':'2026-10-20T17:00:00+05:30'},local,11000))
        self.assertFalse(recently_verified(row,{**local,'error':'stored_schedule_not_visible_in_planner'},11000))
        self.assertFalse(recently_verified(row,local,40000))

    def test_error_diagnostics_never_include_exception_messages_or_paths(self):
        secret = 'private-token-and-caption-must-not-be-logged'
        try:
            raise TimeoutError(secret)
        except TimeoutError as error:
            result = safe_error_diagnostics(error)
        self.assertEqual(result, {'exception_type': 'TimeoutError'})
        self.assertNotIn(secret, json.dumps(result))
        custom = type('UntrustedSensitiveClassName', (Exception,), {})
        self.assertEqual(safe_error_diagnostics(custom(secret)), {'exception_type': 'Exception'})

    def test_only_pending_correlated_runs_get_short_observation_backoff(self):
        for phase in ['accepted', 'dispatch_intent']:
            local = {'error': 'checkpoint_pending_reconciliation',
                     'checkpoints': {'reserve:item:': {'phase': phase}}}
            self.assertEqual(error_backoff_seconds(local), 60)
            self.assertEqual(local['checkpoints']['reserve:item:']['phase'], phase)
        for local in [
            {'error': 'checkpoint_workflow_failed', 'checkpoints': {'x': {'phase': 'failed'}}},
            {'error': 'checkpoint_pending_reconciliation', 'checkpoints': {}},
            {'error': 'browser_login_required', 'checkpoints': {'x': {'phase': 'accepted'}}},
            {'error': 'checkpoint_pending_reconciliation', 'checkpoints': {'x': {'phase': 'failed'}}},
        ]:
            self.assertEqual(error_backoff_seconds(local), 300)

    def test_only_due_approved_native_schedules_are_reconciled(self):
        now=dt.datetime.now(IST)
        row={'externalId':'post','status':'approved','publicationAuthorized':True,'scheduleTimezone':'Asia/Kolkata','nativeHandoff':{'state':'scheduled'},'proposedSchedule':(now-dt.timedelta(minutes=3)).isoformat()}
        invalid=[{**row,'status':'pending_review'},{**row,'publicationAuthorized':False},{**row,'nativeHandoff':None},{**row,'nativeHandoff':{'state':'submitting'}},{**row,'publishedAt':now.isoformat()},{**row,'proposedSchedule':now.isoformat()}]
        self.assertEqual(publication_candidates([row,*invalid],now),[row])

    def test_only_future_owner_approved_posts_are_candidates(self):
        now=dt.datetime.now(IST)
        approved={'externalId':'item','status':'approved','publicationAuthorized':True,'scheduleTimezone':'Asia/Kolkata','proposedSchedule':(now+dt.timedelta(days=1)).isoformat()}
        rows=[approved,{**approved,'status':'pending_review'},{**approved,'publicationAuthorized':False},{**approved,'publishedAt':now.isoformat()},{**approved,'proposedSchedule':(now-dt.timedelta(minutes=1)).isoformat()}]
        self.assertEqual(candidates(rows,now),[approved])

    def test_disabled_mixed_and_cancelled_tests_never_enter_active_work(self):
        now = dt.datetime.now(IST)
        image = {'externalId':'image','status':'approved','publicationAuthorized':True,
                 'scheduleTimezone':'Asia/Kolkata','proposedSchedule':(now+dt.timedelta(days=1)).isoformat()}
        carousel = {**image,'externalId':'funzug-test-2026-10-22-carousel','media_format':'carousel'}
        reel = {**image,'externalId':'funzug-test-2026-10-22-reel','media_format':'reel'}
        old_carousel = {**image,'externalId':'funzug-test-2026-10-16-carousel','media_format':'carousel'}
        old_reel = {**image,'externalId':'funzug-test-2026-10-16-reel','media_format':'reel'}
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(candidates([image,carousel,reel,old_carousel,old_reel],now),[image])
        with patch.dict('os.environ', {'FUNZUG_NATIVE_ACCEPTANCE_ENABLED':'1'}, clear=True):
            self.assertEqual(candidates([image,carousel,reel,old_carousel,old_reel],now),[image,carousel,reel])
        due = [{**row,'nativeHandoff':{'state':'scheduled'},
                'proposedSchedule':(now-dt.timedelta(minutes=3)).isoformat()} for row in [image,carousel,reel,old_carousel,old_reel]]
        with patch.dict('os.environ', {'FUNZUG_NATIVE_MIXED_ENABLED':'1'}, clear=True):
            self.assertEqual(publication_candidates(due,now),due[:3])
            self.assertEqual(candidates([{**reel,'media_format':'image'}],now),[])

    def test_disabled_mixed_poll_never_reads_packages_opens_browser_or_dispatches(self):
        row={'externalId':'news-carousel','media_format':'carousel','status':'approved',
             'publicationAuthorized':True,'scheduleTimezone':'Asia/Kolkata',
             'proposedSchedule':(dt.datetime.now(IST)+dt.timedelta(days=1)).isoformat()}
        with patch.dict('os.environ', {}, clear=True),patch('scheduler.native_runner.read_api',return_value={'drafts':[row]}) as read,patch('scheduler.native_runner.auth') as authenticate,patch('scheduler.native_runner.write_state') as save,patch('scheduler.meta_browser.MetaBrowser') as browser:
            tick({},Path('nonexistent-native-fixture-state.json'),None,True)
        self.assertEqual(read.call_count,1)
        authenticate.assert_not_called()
        browser.assert_not_called()
        self.assertEqual(save.call_args.args[1]['active_item_ids'],[])

    def test_disabled_worker_cannot_open_browser_or_dispatch(self):
        state=Path('nonexistent-native-fixture-state.json')
        with patch('scheduler.native_runner.read_api',return_value={'drafts':[]}),patch('scheduler.native_runner.auth') as authenticate,patch('scheduler.native_runner.write_state') as save:
            tick({},state,None,False)
        authenticate.assert_not_called()
        self.assertFalse(save.call_args.args[1]['enabled'])

    def test_authenticated_packages_can_only_be_requested_from_configured_funzug_origin(self):
        for origin in ['http://funzug.netens.top/api/integrations/funzug','https://other.example/api','https://credential@funzug.netens.top/api','https://funzug.netens.top/api?token=bad']:
            with patch('scheduler.native_runner.request_json') as send:
                with self.assertRaisesRegex(NativeFailure,'invalid_native_api_origin'):read_api({'native_api_url':origin},'native-package',{})
            send.assert_not_called()

    def test_enabled_empty_poll_persists_liveness(self):
        state=Path('nonexistent-native-fixture-state.json')
        with patch('scheduler.native_runner.read_api',return_value={'drafts':[]}),patch('scheduler.native_runner.auth') as authenticate,patch('scheduler.native_runner.write_state') as save:
            tick({},state,None,True)
        authenticate.assert_not_called()
        self.assertTrue(save.call_args.args[1]['enabled'])
        self.assertEqual(save.call_args.args[1]['active_item_ids'],[])
        self.assertGreater(save.call_args.args[1]['last_checked_at'],0)

    def test_due_reconciliation_never_prepares_or_submits_content(self):
        now=dt.datetime.now(IST)
        row={'externalId':'due','status':'approved','publicationAuthorized':True,'scheduleTimezone':'Asia/Kolkata','nativeHandoff':{'state':'scheduled'},'proposedSchedule':(now-dt.timedelta(minutes=3)).isoformat()}
        packet={'fixture':'reviewed'}
        outcome={'platform_results':{'facebook':{'post_id':'123'}}}
        driver=Mock()
        driver.inspect_publication.return_value=outcome
        dispatcher=Mock()
        with patch('scheduler.native_runner.read_api',side_effect=[{'drafts':[row]},packet]),patch('scheduler.native_runner.auth',return_value='fake'),patch('scheduler.native_runner.write_state'),patch('scheduler.native_runner.verify_delivery_package') as verify,patch('scheduler.native_runner.advance') as advance,patch('scheduler.native_runner.CheckpointDispatcher',return_value=dispatcher),patch('scheduler.meta_browser.MetaBrowser',return_value=driver):
            tick({},Path('nonexistent-native-fixture-state.json'),None,True)
        verify.assert_called_once_with(packet,driver)
        dispatcher.assert_called_once_with('published','due',outcome)
        advance.assert_not_called()
        driver.prepare.assert_not_called()
        driver.submit.assert_not_called()

    def test_recorded_complete_publication_clears_stale_local_error_without_meta_access(self):
        published_at='2026-10-14T22:30:00+05:30'
        row={'externalId':'brine','status':'approved','publicationAuthorized':True,
             'publishedAt':published_at,'scheduleTimezone':'Asia/Kolkata',
             'nativeHandoff':{'state':'scheduled'},
             'proposedSchedule':'2026-10-14T22:30:00+05:30'}
        state={'items':{'brine':{'status':'scheduled','error':'checkpoint_pending_reconciliation',
                                'error_diagnostics':{'exception_type':'TimeoutError'},
                                'checkpoints':{'submit:brine':{'phase':'accepted'}}}}}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            path.write_text(json.dumps(state))
            with patch('scheduler.native_runner.read_api',return_value={'drafts':[row]}) as read,\
                 patch('scheduler.native_runner.auth') as authenticate,\
                 patch('scheduler.native_runner.write_state') as save,\
                 patch('scheduler.meta_browser.MetaBrowser') as browser:
                tick({},path,None,True)

        read.assert_called_once()
        authenticate.assert_not_called()
        browser.assert_not_called()
        saved=save.call_args.args[1]
        local=saved['items']['brine']
        self.assertEqual(local['status'],'published')
        self.assertEqual(local['published_at'],published_at)
        self.assertNotIn('error',local)
        self.assertNotIn('error_diagnostics',local)
        self.assertEqual(local['checkpoints'],{'submit:brine':{'phase':'accepted'}})
        self.assertEqual(saved['active_item_ids'],[])


if __name__=='__main__':unittest.main()
