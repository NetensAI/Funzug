import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from scheduler.runner import approved_rows, dispatch, tick, SYNC


class SchedulerTests(unittest.TestCase):
    def test_pending_and_unauthorized_rows_do_not_trigger_due(self):
        for row in ({"status": "pending_review"}, {"status": "approved", "publicationAuthorized": False}):
            self.assertFalse(approved_rows([row], 1900000000)[1])

    def test_published_rows_do_not_trigger_due(self):
        self.assertFalse(approved_rows([{"status": "published", "publicationAuthorized": True}], 1900000000)[1])

    def test_reschedule_changes_event_signature_and_future_post_is_not_due(self):
        row = {"status": "approved", "publicationAuthorized": True, "scheduleTimezone": "Asia/Kolkata", "externalId": "test", "proposedSchedule": "2035-01-01T10:15:00+05:30"}
        first, due = approved_rows([row], 1900000000)
        second, _ = approved_rows([dict(row, proposedSchedule="2035-01-01T11:15:00+05:30")], 1900000000)
        self.assertNotEqual(first, second)
        self.assertFalse(due)

    def test_dispatch_cannot_run_arbitrary_workflow(self):
        with patch("scheduler.runner.build_opener") as request, self.assertRaises(RuntimeError):
            dispatch("approve-scheduled-post.yml", "secret")
        request.assert_not_called()

    def test_ambiguous_dispatch_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key.pem"
            key.write_text("test-key-placeholder")
            state = root / "state.json"
            state.write_text(json.dumps({"jobs": {SYNC: {"baseline": 10, "requested_at": 1900000000, "signature": "old"}}, "synced_signature": "old"}))
            with patch("scheduler.runner.time.time", return_value=1900000100), patch("scheduler.runner.request_json", return_value={"drafts": []}), patch("scheduler.runner.installation_token", return_value="fake-auth"), patch("scheduler.runner.workflow_runs", return_value=[]), patch("scheduler.runner.dispatch") as send:
                tick({"draft_secret": "fake-secret", "key_file": str(key)}, state)
            send.assert_not_called()
            self.assertIn(SYNC, json.loads(state.read_text())["jobs"])

    def test_new_approval_waits_for_sync_before_publisher(self):
        row = {"status": "approved", "publicationAuthorized": True, "scheduleTimezone": "Asia/Kolkata", "externalId": "test", "proposedSchedule": "2026-10-11T23:30:00+05:30"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key.pem"
            key.write_text("test-key-placeholder")
            state = root / "state.json"
            with patch("scheduler.runner.time.time", return_value=1900000100), patch("scheduler.runner.request_json", return_value={"drafts": [row]}), patch("scheduler.runner.installation_token", return_value="fake-auth"), patch("scheduler.runner.workflow_runs", return_value=[]), patch("scheduler.runner.dispatch") as send:
                tick({"draft_secret": "fake-secret", "key_file": str(key)}, state)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0], SYNC)


if __name__ == "__main__":
    unittest.main()
