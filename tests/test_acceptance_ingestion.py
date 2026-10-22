import copy
import unittest
from unittest.mock import patch
from scripts import brandflow_sync as sync


class FrozenDateTime(sync.dt.datetime):
    @classmethod
    def now(cls, tz=None):
        moment = cls(2026, 10, 22, 19, 0, tzinfo=sync.SCHEDULE_TIMEZONE)
        return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)


class AcceptanceIngestionTests(unittest.TestCase):
    def fixture(self):
        return {'items':[{'id':f'funzug-test-2026-10-22-{kind}','format':kind,'status':'draft','scheduled_at':slot,'platforms':['facebook','instagram']} for kind,slot in [('carousel','2026-10-22T20:00:00+05:30'),('reel','2026-10-22T20:15:00+05:30')]]}

    def test_only_authorized_test_items_can_be_selected(self):
        original=self.fixture()
        with patch.object(sync.pipeline,'load_json',return_value=original):
            self.assertEqual(sync.acceptance_inbox(),original)
        for mutate in (lambda q:q['items'].append(q['items'][0]),lambda q:q['items'][0].update(status='approved'),lambda q:q['items'][0].update(scheduled_at='2099-01-01T20:00:00+05:30'),lambda q:q['items'][0].update(platforms=['facebook'])):
            changed=copy.deepcopy(original);mutate(changed)
            with patch.object(sync.pipeline,'load_json',return_value=changed):
                with self.assertRaises(RuntimeError):sync.acceptance_inbox()

    def test_test_sync_does_not_load_or_update_news_inbox(self):
        inbox=self.fixture()
        with patch.object(sync,'secret',return_value='private-fixture'),patch.object(sync,'api_url',return_value='https://funzug.netens.top/api/integrations/funzug/drafts'),patch.object(sync,'acceptance_inbox',return_value=inbox),patch.object(sync.pipeline,'validate_draft_queue',return_value=[]),patch.object(sync.pipeline,'load_json') as read_news,patch.object(sync,'api_status',return_value={}),patch.object(sync,'payload_for',side_effect=lambda item:{'fixture':item['id']}),patch.object(sync,'api_request') as send:
            sync.sync_pending(acceptance_tests=True)
        read_news.assert_not_called()
        self.assertEqual(send.call_count,2)

    def test_only_dashboard_approved_acceptance_item_is_consumed(self):
        inbox=self.fixture();item=inbox['items'][0]
        news={'items':[{'id':'news-pending','status':'draft'}]};before=copy.deepcopy(news)
        row={'status':'approved','publicationAuthorized':True,'scheduleTimezone':'Asia/Kolkata','proposedSchedule':item['scheduled_at'],'reviewedBy':'owner','reviewedAt':'2026-10-14T11:00:00+05:30','reviewNote':'Authorized test','contentHash':'a'*64}
        with patch.dict('os.environ',{'FUNZUG_DELIVERY_MODE':'meta_native'}),patch.object(sync,'secret',return_value='fixture'),patch.object(sync,'api_url',return_value='https://funzug.netens.top/api/integrations/funzug/drafts'),patch.object(sync,'api_status',return_value={item['id']:row}),patch.object(sync,'acceptance_inbox',return_value=inbox),patch.object(sync.pipeline,'load_json',side_effect=[news,{'items':[]},{'items':[]}]),patch.object(sync,'require_matching_approved_content') as match,patch.object(sync,'approve_native_draft') as approve,patch.object(sync.pipeline,'host_and_approve_draft') as public_upload:
            with patch.object(sync.dt, 'datetime', FrozenDateTime):
                sync.process_approvals()
        self.assertEqual(news,before)
        match.assert_called_once()
        self.assertEqual(approve.call_count,1)
        self.assertEqual(approve.call_args.args[2],item['id'])
        self.assertEqual(approve.call_args.args[-1],row['contentHash'])
        public_upload.assert_not_called()

    def test_cancelled_test_approvals_are_ignored(self):
        news={'items':[{'id':'news-pending','status':'draft'}]}
        for identifier,slot in [('funzug-test-2026-10-16-carousel','2026-10-16T20:00:00+05:30'),('funzug-test-2026-10-16-reel','2026-10-16T20:15:00+05:30')]:
            row={'status':'approved','publicationAuthorized':True,'scheduleTimezone':'Asia/Kolkata','proposedSchedule':slot}
            with patch.object(sync,'secret',return_value='fixture'),patch.object(sync,'api_url',return_value='https://funzug.netens.top/api/integrations/funzug/drafts'),patch.object(sync,'api_status',return_value={identifier:row}),patch.object(sync.pipeline,'load_json',return_value=news),patch.object(sync,'approve_native_draft') as approve,patch.object(sync.pipeline,'host_and_approve_draft') as public_upload:
                sync.process_approvals()
            approve.assert_not_called()
            public_upload.assert_not_called()
