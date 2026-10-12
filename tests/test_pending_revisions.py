import unittest
from unittest.mock import patch
import scripts.brandflow_sync as sync


class PendingRevisionTests(unittest.TestCase):
    def sent(self, row, enabled):
        with patch.object(sync, 'secret', return_value='unused'), patch.object(sync, 'api_url', return_value='https://example.invalid'), patch.object(sync.pipeline, 'load_json', return_value={'items': [{'id': 'item'}]}), patch.object(sync.pipeline, 'validate_draft_queue', return_value=[]), patch.object(sync, 'api_status', return_value={'item': row}), patch.object(sync, 'payload_for', return_value={}), patch.object(sync, 'api_request') as request:
            sync.sync_pending(enabled)
            return request.call_count

    def test_explicit_pending_revision_only(self):
        row = {'status': 'pending_review', 'publicationAuthorized': False, 'publishedAt': None}
        self.assertEqual(self.sent(row, False), 0)
        self.assertEqual(self.sent(row, True), 1)

    def test_reviewed_or_ambiguous_content_is_never_rewritten(self):
        for row in [{'status': 'approved', 'publicationAuthorized': True}, {'status': 'rejected', 'publicationAuthorized': False}, {'status': 'pending_review'}, {'status': 'pending_review', 'publicationAuthorized': False, 'publishedAt': '2026-10-11T23:30:00+05:30'}]:
            with self.subTest(row=row):
                self.assertEqual(self.sent(row, True), 0)
