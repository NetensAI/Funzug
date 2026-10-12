import unittest
from unittest.mock import patch

import scripts.brandflow_sync as sync


class BrandFlowRescheduleTests(unittest.TestCase):
    def test_native_handoff_cannot_be_rescheduled_without_reconciliation(self):
        import copy
        item={"id":"native-fixture","status":"approved","scheduled_at":"2999-11-12T19:15:00+05:30","approval":{"status":"approved"},"native_handoff":{"state":"uncertain"}}
        before=copy.deepcopy(item)
        with self.assertRaisesRegex(RuntimeError,"native Meta handoff"):
            sync.reschedule_approved_item({"items":[item]},item["id"],"2999-11-13T19:45:00+05:30","owner","New time","2026-10-12T13:30:00+05:30")
        self.assertEqual(item,before)

    def test_reschedule_refuses_any_recorded_platform_result_without_mutation(self):
        import copy
        for result in [{"status": "published", "post_id": "existing"}, {"status": "failed"}]:
            item = {
                "id": "attempted-post", "status": "approved",
                "scheduled_at": "2999-11-12T19:15:00+05:30",
                "approval": {"status": "approved"},
                "platform_results": {"instagram": result},
            }
            before = copy.deepcopy(item)
            with self.assertRaisesRegex(RuntimeError, "platform-specific recovery"):
                sync.reschedule_approved_item(
                    {"items": [item]}, item["id"], "2999-11-13T19:45:00+05:30",
                    "owner", "Requested new time", "2026-10-12T11:00:00+05:30",
                )
            self.assertEqual(item, before)

    def test_explicit_new_brandflow_review_updates_existing_approved_schedule(self):
        item_id = "funzug-example-1"
        item = {
            "id": item_id,
            "status": "approved",
            "scheduled_at": "2999-11-12T19:15:00+05:30",
            "approval": {
                "status": "approved",
                "approved_by": "vatsal",
                "approved_at": "2026-10-11T10:00:00Z",
                "note": "Original approval",
                "review_checklist": {"approvalConfirmed": True},
            },
        }
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": [item]}
        status = {
            "status": "approved",
            "publicationAuthorized": True,
            "reviewChecks": {},
            "scheduleTimezone": "Asia/Kolkata",
            "proposedSchedule": "2999-11-13T19:45:00+05:30",
            "reviewedBy": "vatsal",
            "reviewNote": "Rescheduled at owner request",
            "reviewedAt": "2026-10-11T15:00:00Z",
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api"),
            patch.object(sync, "api_status", return_value={item_id: status}),
            patch.object(sync.pipeline, "load_json", side_effect=[{"items": []}, queue]),
            patch.object(sync.pipeline, "save_json") as save,
            patch.object(sync.pipeline, "log_event") as log,
            patch.object(sync.pipeline, "host_and_approve_draft") as upload,
        ):
            sync.process_approvals()
        self.assertEqual(item["scheduled_at"], "2999-11-13T19:45:00+05:30")
        self.assertEqual(item["approval"]["schedule_changes"][0]["changed_by"], "vatsal")
        self.assertEqual(log.call_args.args[0]["event"], "schedule_rescheduled")
        save.assert_called_once_with(sync.pipeline.QUEUE_PATH, queue)
        upload.assert_not_called()

    def test_reschedule_refuses_published_items_and_past_times(self):
        item = {
            "id": "funzug-example-1",
            "status": "published",
            "scheduled_at": "2999-11-12T19:15:00+05:30",
            "approval": {"status": "approved"},
        }
        with self.assertRaisesRegex(RuntimeError, "approved, unpublished"):
            sync.reschedule_approved_item(
                {"items": [item]}, item["id"], "2999-11-13T19:45:00+05:30",
                "vatsal", "Requested new time", "2026-10-11T15:00:00Z",
            )
        item["status"] = "approved"
        with self.assertRaisesRegex(RuntimeError, "must be in the future"):
            sync.reschedule_approved_item(
                {"items": [item]}, item["id"], "2000-01-01T00:00:00Z",
                "vatsal", "Requested new time", "2026-10-11T15:00:00Z",
            )

    def test_reschedule_requires_a_new_review_timestamp(self):
        item_id = "funzug-example-1"
        queue = {"items": [{
            "id": item_id,
            "status": "approved",
            "scheduled_at": "2999-11-12T19:15:00+05:30",
            "approval": {"status": "approved", "approved_at": "2026-10-11T15:00:00Z"},
        }]}
        status = {
            "status": "approved",
            "publicationAuthorized": True,
            "reviewChecks": {},
            "scheduleTimezone": "Asia/Kolkata",
            "proposedSchedule": "2999-11-13T19:45:00+05:30",
            "reviewedBy": "vatsal",
            "reviewNote": "Original approval",
            "reviewedAt": "2026-10-11T15:00:00Z",
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api"),
            patch.object(sync, "api_status", return_value={item_id: status}),
            patch.object(sync.pipeline, "load_json", side_effect=[{"items": []}, queue]),
        ):
            with self.assertRaisesRegex(RuntimeError, "no new BrandFlow review timestamp"):
                sync.process_approvals()


if __name__ == "__main__":
    unittest.main()
