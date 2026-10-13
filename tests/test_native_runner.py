import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scheduler.native_runner import candidates,read_api,tick
from scheduler.native_worker import IST,NativeFailure


class NativeRunnerTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
