import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import funzug_pipeline as pipeline


class ValidationTests(unittest.TestCase):
    def test_empty_actions_variable_defaults_graph_api_version(self):
        self.assertEqual(pipeline.GRAPH_VERSION, "v26.0")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.root = Path(self.temp.name)
        image = self.root / "assets" / "post.png"
        image.parent.mkdir()
        header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
        image.write_bytes(header + struct.pack(">II", 1080, 1350) + b"\x08\x06\x00\x00\x00")
        self.item = {
            "id": "funzug-2026-10-11-example",
            "status": "draft",
            "format": "image",
            "headline": "A supported headline",
            "caption": "A verified caption.",
            "topic_key": "example-story",
            "platforms": ["facebook", "instagram"],
            "scheduled_at": "2026-10-11T12:00:00-04:00",
            "media_path": "assets/post.png",
            "public_media_url": "https://cdn.example.com/post.png",
            "claims": [{"text": "The supported fact.", "source_ids": ["source-1"]}],
            "sources": [{
                "id": "source-1",
                "title": "Primary source",
                "publisher": "Example Institute",
                "url": "https://example.com/research",
                "published_at": "2026-10-10T09:00:00Z",
                "checked_at": "2026-10-10T10:00:00Z",
            }],
        }
        self.root_patch = patch.object(pipeline, "ROOT", self.root)
        self.history_patch = patch.object(pipeline, "HISTORY_PATH", self.root / "history.json")
        self.root_patch.start()
        self.history_patch.start()

    def tearDown(self):
        self.history_patch.stop()
        self.root_patch.stop()
        self.temp.cleanup()

    def test_valid_item_meets_image_and_source_requirements(self):
        self.assertEqual(pipeline.validate_item(self.item, (1080, 1350)), [])

    def test_rejects_wrong_image_dimensions(self):
        image = self.root / "assets" / "post.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 1080, 1080) + b"\x08\x06\x00\x00\x00")
        self.assertTrue(any("1080x1350" in error for error in pipeline.validate_item(self.item, (1080, 1350))))

    def test_requires_local_image_and_safe_public_url(self):
        item = dict(self.item, media_path=None, public_media_url="https://cdn.example.com/post.png?token=private")
        errors = pipeline.validate_item(item, (1080, 1350))
        self.assertTrue(any("media_path is required" in error for error in errors))
        self.assertTrue(any("query strings" in error for error in errors))

    def test_rejects_unverified_claim(self):
        item = json.loads(json.dumps(self.item))
        item["claims"][0]["source_ids"] = ["missing-source"]
        self.assertTrue(any("unknown source references" in error for error in pipeline.validate_item(item, (1080, 1350))))

    def test_published_topic_in_history_does_not_break_future_validation(self):
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": [dict(self.item, status="published", approval={
            "status": "approved",
            "approved_by": "Vatsal",
            "approved_at": "2026-10-10T10:00:00Z",
            "note": "Reviewed",
        })]}
        (self.root / "history.json").write_text(json.dumps({"topic_keys": ["example-story"]}), encoding="utf-8")
        self.assertEqual(pipeline.validate_queue(queue), [])

    def test_rejects_malformed_platforms_without_crashing(self):
        item = dict(self.item, platforms=[["unexpected"]])
        errors = pipeline.validate_item(item, (1080, 1350))
        self.assertTrue(any("platform must be facebook or instagram" in error for error in errors))

    def test_rejects_approval_without_a_reviewer_note_or_timestamp(self):
        item = dict(self.item, status="approved", approval={"status": "approved", "approved_by": "Vatsal"})
        errors = pipeline.validate_item(item, (1080, 1350))
        self.assertTrue(any("review note" in error for error in errors))
        self.assertTrue(any("approved_at" in error for error in errors))

    def test_draft_never_calls_meta_publisher_even_when_execute_is_requested(self):
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": [self.item]}
        with patch.object(pipeline, "MetaPublisher") as publisher:
            self.assertEqual(pipeline.publish_due(queue, execute=True, confirmation="FUNZUG"), 0)
            publisher.assert_not_called()

    def test_error_sanitizer_removes_access_tokens(self):
        message = "bad access_token=EAAExample0123456789012345678901&other=1"
        self.assertNotIn("EAAExample", pipeline.safe_error_message(message))
        self.assertIn("[REDACTED]", pipeline.safe_error_message(message))


if __name__ == "__main__":
    unittest.main()
