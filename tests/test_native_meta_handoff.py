import copy
import datetime as dt
import unittest
from unittest.mock import patch

from scripts.native_meta_handoff import reserve, begin_submission, record_receipt, record_published_outcomes
import funzug_pipeline as pipeline


class NativeHandoffTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime.fromisoformat("2026-10-12T14:00:00+05:30")
        self.item = {"id":"fixture", "status":"approved", "format":"image", "platforms":["facebook","instagram"], "scheduled_at":"2026-10-13T18:00:00+05:30", "approval":{"status":"approved", "review_checklist":{"approvalConfirmed":True}}}
        self.row = {"status":"approved", "publicationAuthorized":True, "scheduleTimezone":"Asia/Kolkata", "proposedSchedule":self.item["scheduled_at"], "contentHash":"a"*64}
        self.hash_check = patch("scripts.native_meta_handoff.sync.require_matching_approved_content")
        self.hash_check.start()
        self.addCleanup(self.hash_check.stop)

    def test_reservation_preserves_review_and_slot_and_blocks_publisher(self):
        approval = copy.deepcopy(self.item["approval"])
        self.assertTrue(reserve(self.item,self.row,self.now))
        self.assertFalse(pipeline.workflow_delivery_allowed(self.item))
        self.assertEqual(self.item["approval"],approval)
        self.assertEqual(self.item["native_handoff"]["scheduled_at"],self.row["proposedSchedule"])
        self.assertFalse(reserve(self.item,self.row,self.now))

    def test_rejections_do_not_mutate_post(self):
        for field,value in [("status","draft"),("publicationAuthorized",False),("scheduleTimezone","UTC"),("proposedSchedule","2026-10-14T18:00:00+05:30")]:
            row = dict(self.row,**{field:value})
            before = copy.deepcopy(self.item)
            with self.assertRaises((RuntimeError,ValueError)):
                reserve(self.item,row,self.now)
            self.assertEqual(self.item,before)

    def test_due_posts_outcomes_and_uncertain_handoffs_cannot_be_reserved(self):
        for changes in [{"scheduled_at":self.now.isoformat()},{"platform_results":{"instagram":{"status":"published"}}},{"native_handoff":{"state":"uncertain"}},{"delivery_mode":"unexpected"},{"format":"carousel"}]:
            item = dict(self.item,**changes)
            before = copy.deepcopy(item)
            with self.assertRaises(RuntimeError):
                reserve(item,self.row,self.now)
            self.assertEqual(item,before)

    def test_content_mismatch_cannot_disable_existing_delivery(self):
        with patch("scripts.native_meta_handoff.sync.require_matching_approved_content",side_effect=RuntimeError("content mismatch")):
            with self.assertRaisesRegex(RuntimeError,"content mismatch"):
                reserve(self.item,self.row,self.now)
        self.assertTrue(pipeline.workflow_delivery_allowed(self.item))

    def test_submission_cannot_be_repeated_and_receipts_keep_workflow_blocked(self):
        reserve(self.item,self.row,self.now)
        begin_submission(self.item,self.now)
        with self.assertRaises(RuntimeError):
            begin_submission(self.item,self.now)
        for platform in self.item["platforms"]:
            record_receipt(self.item,{"platform":platform,"schedule_id":"observed-"+platform,"scheduled_at":self.item["scheduled_at"],"content_hash":self.row["contentHash"],"planner_url":"https://business.facebook.com/latest/content","checked_at":self.now.isoformat()},self.now)
        self.assertEqual(self.item["native_handoff"]["state"],"scheduled")
        self.assertFalse(pipeline.workflow_delivery_allowed(self.item))

    def test_receipt_cannot_precede_submission_or_change_slot(self):
        reserve(self.item,self.row,self.now)
        receipt={"platform":"instagram","schedule_id":"observed","scheduled_at":self.item["scheduled_at"],"content_hash":self.row["contentHash"],"planner_url":"https://business.facebook.com/latest/content","checked_at":self.now.isoformat()}
        with self.assertRaises(RuntimeError):
            record_receipt(self.item,receipt,self.now)
        begin_submission(self.item,self.now)
        for field,value in [("scheduled_at","2026-10-14T18:00:00+05:30"),("platform","unexpected"),("content_hash","b"*64),("planner_url","https://attacker.example"),("checked_at","2026-10-12T13:00:00+05:30")]:
            with self.assertRaises(RuntimeError):
                record_receipt(self.item,dict(receipt,**{field:value}),self.now)
        self.assertEqual(self.item["native_handoff"]["receipts"],{})

    def test_observed_receipt_replaces_placeholder_and_requires_all_real_ids(self):
        reserve(self.item,self.row,self.now)
        begin_submission(self.item,self.now)
        handoff = self.item["native_handoff"]
        handoff["state"] = "scheduled"
        handoff["receipts"] = {
            platform: {
                "platform": platform,
                "schedule_id": f"meta-planner-visible:fixture:{platform}",
                "scheduled_at": handoff["scheduled_at"],
                "content_hash": handoff["content_hash"],
                "planner_url": "https://business.facebook.com/latest/content_calendar",
                "checked_at": self.now.isoformat(),
            }
            for platform in self.item["platforms"]
        }
        actual = {"platform":"facebook", "schedule_id":"1519859980179026", "scheduled_at":handoff["scheduled_at"], "content_hash":handoff["content_hash"], "planner_url":"https://business.facebook.com/latest/content_calendar?business_id=123&asset_id=456", "checked_at":self.now.isoformat()}

        record_receipt(self.item,actual,self.now)
        self.assertEqual(handoff["receipts"]["facebook"]["schedule_id"],"1519859980179026")
        self.assertEqual(handoff["state"],"submitting")

        with self.assertRaisesRegex(RuntimeError,"conflicting receipt"):
            record_receipt(self.item,dict(actual,schedule_id="another-actual-id"),self.now)

        instagram = dict(actual,platform="instagram",schedule_id="18121810900845217")
        record_receipt(self.item,instagram,self.now)
        self.assertEqual(handoff["state"],"scheduled")

    def test_published_outcomes_require_matching_meta_receipts_and_verified_detail_urls(self):
        reserve(self.item,self.row,self.now)
        begin_submission(self.item,self.now)
        post_ids = {"facebook":"1519859980179026", "instagram":"18121810900845217"}
        for platform, post_id in post_ids.items():
            record_receipt(self.item, {
                "platform":platform,
                "schedule_id":post_id,
                "scheduled_at":self.item["scheduled_at"],
                "content_hash":self.row["contentHash"],
                "planner_url":f"https://business.facebook.com/latest/insights/object_insights/?content_id={post_id}",
                "checked_at":self.now.isoformat(),
            },self.now)
        published_now = dt.datetime.fromisoformat("2026-10-13T18:05:00+05:30")
        raw = {"platform_results": {
            platform: {
                "post_id":post_id,
                "published_at":"2026-10-13T18:00:00+05:30",
                "evidence_url":f"https://business.facebook.com/latest/insights/object_insights/?content_id={post_id}",
            }
            for platform,post_id in post_ids.items()
        }}

        for bad in [
            {"platform_results":{"facebook":raw["platform_results"]["facebook"]}},
            {"platform_results":{**raw["platform_results"],"facebook":dict(raw["platform_results"]["facebook"],post_id="different-id")}},
            {"platform_results":{**raw["platform_results"],"instagram":dict(raw["platform_results"]["instagram"],published_at="2026-10-13T19:00:00+05:30")}},
            {"platform_results":{**raw["platform_results"],"facebook":dict(raw["platform_results"]["facebook"],evidence_url="https://attacker.example/latest/insights/object_insights/?content_id=1519859980179026")}},
        ]:
            before = copy.deepcopy(self.item)
            with self.assertRaises(RuntimeError):
                record_published_outcomes(self.item,bad,published_now)
            self.assertEqual(self.item,before)

        self.assertTrue(record_published_outcomes(self.item,raw,published_now))
        self.assertEqual(self.item["status"],"published")
        self.assertEqual(self.item["platform_results"]["facebook"]["post_id"],post_ids["facebook"])
        self.assertFalse(record_published_outcomes(self.item,raw,published_now))
