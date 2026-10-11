import unittest
from unittest.mock import patch

import funzug_pipeline as pipeline


class FailedFacebookRetryTests(unittest.TestCase):
    def item(self):
        return {
            "id": "ice-post",
            "topic_key": "ice-topic",
            "status": "failed",
            "platforms": ["facebook"],
            "scheduled_at": "2000-01-01T05:30:00+05:30",
            "platform_results": {
                "facebook": {"status": "failed"},
                "instagram": {"status": "published", "post_id": "existing-ig-post"},
            },
            "approval": {"retry_authorizations": []},
        }

    def test_requires_owner_authorization_before_meta_access(self):
        item = self.item()
        queue = {"items": [item]}
        with patch.object(pipeline, "validate_queue", return_value=[]), patch.object(pipeline, "MetaPublisher") as publisher:
            with self.assertRaisesRegex(RuntimeError, "explicit owner authorization"):
                pipeline.retry_failed_facebook(queue, item["id"])
            publisher.assert_not_called()
        self.assertEqual(item["status"], "failed")

    def test_targets_only_failed_facebook_and_preserves_instagram_result(self):
        item = self.item()
        item["approval"]["retry_authorizations"] = [{
            "authorized_by": "owner",
            "platforms": ["facebook"],
            "topic_key": item["topic_key"],
        }]
        other = {"id": "different-post", "status": "approved"}
        queue = {"items": [item, other]}
        with patch.object(pipeline, "validate_queue", return_value=[]), patch.object(pipeline, "MetaPublisher") as publisher:
            with patch.object(pipeline, "log_event") as log, patch.object(pipeline, "publish_due", return_value=0) as publish:
                self.assertEqual(pipeline.retry_failed_facebook(queue, item["id"]), 0)
        publisher.return_value.facebook_page_token.assert_called_once_with()
        publish.assert_called_once_with(queue, True, "FUNZUG", item_id=item["id"])
        self.assertEqual(item["status"], "approved")
        self.assertEqual(item["platform_results"]["instagram"]["post_id"], "existing-ig-post")
        self.assertEqual(other["status"], "approved")
        self.assertEqual(log.call_args.args[0]["event"], "retry_started")


if __name__ == "__main__":
    unittest.main()
