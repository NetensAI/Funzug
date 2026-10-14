import copy
import unittest
from unittest.mock import patch
from scripts import brandflow_sync as sync


class AcceptanceIngestionTests(unittest.TestCase):
    def fixture(self):
        return {'items':[{'id':f'funzug-test-2026-10-16-{kind}','format':kind,'status':'draft','scheduled_at':slot,'platforms':['facebook','instagram']} for kind,slot in [('carousel','2026-10-16T20:00:00+05:30'),('reel','2026-10-16T20:15:00+05:30')]]}

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
