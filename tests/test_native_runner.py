import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock

from scheduler.native_runner import candidates,publication_candidates,read_api,tick
from scheduler.native_worker import IST,NativeFailure


class NativeRunnerTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
