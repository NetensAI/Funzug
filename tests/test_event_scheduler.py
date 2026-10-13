import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from scheduler.runner import approved_rows, dispatch, tick, SYNC, PUBLISH


class SchedulerTests(unittest.TestCase):
    def test_pending_and_unauthorized_rows_do_not_trigger_due(self):
        for row in ({"status": "pending_review"}, {"status": "approved", "publicationAuthorized": False}):
            self.assertFalse(approved_rows([row], 1900000000)[1])

    def test_published_rows_do_not_trigger_due(self):
        self.assertFalse(approved_rows([{"status": "published", "publicationAuthorized": True}], 1900000000)[1])

    def test_native_handoff_rows_do_not_trigger_api_publishing(self):
        for state in ("reserved", "submitting", "scheduled"):
            row = {
                "status": "approved",
                "publicationAuthorized": True,
                "scheduleTimezone": "Asia/Kolkata",
                "externalId": "native-" + state,
                "proposedSchedule": "2026-10-11T23:30:00+05:30",
                "nativeHandoff": {"state": state},
            }
            self.assertFalse(approved_rows([row], 1900000000)[1], state)

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

    def test_failed_publisher_requests_result_sync_not_post_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key.pem"
            key.write_text("test-key-placeholder")
            state = root / "state.json"
            state.write_text(json.dumps({"jobs": {PUBLISH: {"baseline": 10, "requested_at": 1900000000, "signature": "old", "run_id": 11}}, "synced_signature": "old"}))
            run = {"id": 11, "status": "completed", "conclusion": "failure", "actor": {"login": "funzug-automation-netensai[bot]"}}
            with patch("scheduler.runner.time.time", return_value=1900000100), patch("scheduler.runner.request_json", return_value={"drafts": []}), patch("scheduler.runner.installation_token", return_value="fake-auth"), patch("scheduler.runner.workflow_runs", side_effect=lambda workflow, auth: [run] if workflow == PUBLISH else []), patch("scheduler.runner.dispatch") as send:
                tick({"draft_secret": "fake-secret", "key_file": str(key)}, state)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[0], SYNC)
            self.assertIn("failed", json.loads(state.read_text())["error"])

    def test_successful_sync_clears_its_stale_failure_and_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key.pem"
            key.write_text("test-key-placeholder")
            state = root / "state.json"
            state.write_text(json.dumps({
                "jobs": {SYNC: {"baseline": 10, "requested_at": 1900000000, "signature": approved_rows([], 1900000100)[0], "run_id": 11}},
                "synced_signature": "old",
                "error": SYNC + " failed; run_id=9",
                "cooldown_until": {SYNC: 1900000300},
            }))
            run = {"id": 11, "status": "completed", "conclusion": "success", "actor": {"login": "funzug-automation-netensai[bot]"}}
            with patch("scheduler.runner.time.time", return_value=1900000100), patch("scheduler.runner.request_json", return_value={"drafts": []}), patch("scheduler.runner.installation_token", return_value="fake-auth"), patch("scheduler.runner.workflow_runs", side_effect=lambda workflow, auth: [run] if workflow == SYNC else []), patch("scheduler.runner.dispatch") as send:
                tick({"draft_secret": "fake-secret", "key_file": str(key)}, state)
            saved = json.loads(state.read_text())
            self.assertNotIn("error", saved)
            self.assertNotIn(SYNC, saved["cooldown_until"])
            send.assert_not_called()

    def test_later_sync_success_clears_stale_failure_without_pending_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "key.pem"
            key.write_text("test-key-placeholder")
            state = root / "state.json"
            signature = approved_rows([], 1900000100)[0]
            state.write_text(json.dumps({
                "jobs": {},
                "synced_signature": signature,
                "error": SYNC + " failed; run_id=9",
                "cooldown_until": {SYNC: 1900000300},
            }))
            failed = {"id": 9, "status": "completed", "conclusion": "failure", "actor": {"login": "funzug-automation-netensai[bot]"}}
            succeeded = {"id": 11, "status": "completed", "conclusion": "success", "actor": {"login": "funzug-automation-netensai[bot]"}}
            with patch("scheduler.runner.time.time", return_value=1900000100), patch("scheduler.runner.request_json", return_value={"drafts": []}), patch("scheduler.runner.installation_token", return_value="fake-auth"), patch("scheduler.runner.workflow_runs", side_effect=lambda workflow, auth: [failed, succeeded] if workflow == SYNC else []), patch("scheduler.runner.dispatch") as send:
                tick({"draft_secret": "fake-secret", "key_file": str(key)}, state)
            saved = json.loads(state.read_text())
            self.assertNotIn("error", saved)
            self.assertNotIn(SYNC, saved["cooldown_until"])
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
