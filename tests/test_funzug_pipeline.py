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
            "claims": [{"text": "The supported fact.", "source_ids": ["source-1"], "support_note": "The cited source directly reports this fact."}],
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
        self.draft_queue_patch = patch.object(pipeline, "DRAFT_QUEUE_PATH", self.root / "drafts" / "queue.json")
        self.root_patch.start()
        self.history_patch.start()
        self.draft_queue_patch.start()

    def tearDown(self):
        self.draft_queue_patch.stop()
        self.history_patch.stop()
        self.root_patch.stop()
        self.temp.cleanup()

    def test_valid_item_meets_image_and_source_requirements(self):
        self.assertEqual(pipeline.validate_item(self.item, (1080, 1350)), [])

    def carousel_item(self):
        item = json.loads(json.dumps(self.item))
        item["format"] = "carousel"
        item.pop("media_path")
        item.pop("public_media_url")
        item["media_paths"] = ["assets/post.png", "assets/slide-2.png"]
        item["public_media_urls"] = [
            "https://cdn.example.com/slide-1.png",
            "https://cdn.example.com/slide-2.png",
        ]
        (self.root / "assets" / "slide-2.png").write_bytes((self.root / "assets" / "post.png").read_bytes())
        return item

    def test_valid_carousel_checks_every_slide_and_url(self):
        self.assertEqual(pipeline.validate_item(self.carousel_item(), (1080, 1350)), [])

    def test_carousel_requires_two_to_ten_slides_and_matching_urls(self):
        item = self.carousel_item()
        item["media_paths"] = ["assets/slide-1.png"]
        item["public_media_urls"] = ["https://cdn.example.com/slide-1.png"]
        self.assertTrue(any("2 to 10" in error for error in pipeline.validate_item(item, (1080, 1350))))
        item = self.carousel_item()
        item["public_media_urls"].append("https://cdn.example.com/slide-3.png")
        errors = pipeline.validate_item(item, (1080, 1350))
        self.assertTrue(any("match media_paths" in error for error in errors))

    def test_carousel_draft_allows_missing_public_urls_but_checks_images(self):
        item = self.carousel_item()
        item.pop("public_media_urls")
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": [item]}
        self.assertEqual(pipeline.validate_draft_queue(queue), [])

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

    def test_requires_claim_level_source_support_note(self):
        item = json.loads(json.dumps(self.item))
        del item["claims"][0]["support_note"]
        self.assertTrue(any("support_note" in error for error in pipeline.validate_item(item, (1080, 1350))))

    def test_draft_inbox_allows_missing_public_url_but_checks_image_and_sources(self):
        draft = json.loads(json.dumps(self.item))
        draft.pop("public_media_url")
        drafts = {"brand": {"required_image_size": [1080, 1350]}, "items": [draft]}
        self.assertEqual(pipeline.validate_draft_queue(drafts), [])

    def test_draft_inbox_rejects_approved_status(self):
        draft = json.loads(json.dumps(self.item))
        draft.pop("public_media_url")
        draft["status"] = "approved"
        drafts = {"brand": {"required_image_size": [1080, 1350]}, "items": [draft]}
        self.assertTrue(any("draft status only" in error for error in pipeline.validate_draft_queue(drafts)))

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


    def approved_item(self, scheduled_at="2000-01-01T00:00:00Z"):
        item = json.loads(json.dumps(self.item))
        item["status"] = "approved"
        item["scheduled_at"] = scheduled_at
        item["approval"] = {
            "status": "approved",
            "approved_by": "Vatsal",
            "approved_at": "2000-01-01T00:00:00Z",
            "note": "Reviewed sources, caption, image, platforms, and schedule",
        }
        return item

    def test_future_approved_post_is_not_published(self):
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": [self.approved_item("2999-01-01T00:00:00Z")]}
        with patch.object(pipeline, "MetaPublisher") as publisher:
            self.assertEqual(pipeline.publish_due(queue, execute=True, confirmation="FUNZUG"), 0)
            publisher.assert_not_called()

    def test_due_post_requires_explicit_publish_confirmation(self):
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": [self.approved_item()]}
        with patch.object(pipeline, "MetaPublisher") as publisher:
            with self.assertRaisesRegex(RuntimeError, "publishing requires --confirm-publish FUNZUG"):
                pipeline.publish_due(queue, execute=True, confirmation=None)
            publisher.assert_not_called()

    def test_approval_is_saved_with_reviewer_and_audit_event(self):
        queue_path = self.root / "queue.json"
        log_path = self.root / "logs" / "events.jsonl"
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": [self.item]}
        with patch.object(pipeline, "QUEUE_PATH", queue_path), patch.object(pipeline, "LOG_PATH", log_path):
            pipeline.approve(queue, self.item["id"], "Vatsal", "Reviewed sources, caption, image, platforms, and schedule")
        saved = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["items"][0]["approval"]["approved_by"], "Vatsal")
        event = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(event["event"], "approved")
        self.assertEqual(event["item_id"], self.item["id"])

    def test_mocked_publish_updates_status_history_and_audit_log(self):
        queue_path = self.root / "queue.json"
        log_path = self.root / "logs" / "events.jsonl"
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": [self.approved_item()]}
        mock_publisher = patch.object(pipeline, "MetaPublisher").start()
        instance = mock_publisher.return_value
        instance.publish_facebook_image.return_value = {"post_id": "fb-test-post"}
        instance.publish_instagram_image.return_value = {"id": "ig-test-post"}
        try:
            with patch.object(pipeline, "QUEUE_PATH", queue_path), patch.object(pipeline, "LOG_PATH", log_path):
                self.assertEqual(pipeline.publish_due(queue, execute=True, confirmation="FUNZUG"), 0)
        finally:
            mock_publisher.stop()
        saved = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["items"][0]["status"], "published")
        self.assertEqual(saved["items"][0]["platform_results"]["facebook"]["post_id"], "fb-test-post")
        self.assertEqual(saved["items"][0]["platform_results"]["instagram"]["post_id"], "ig-test-post")
        history = json.loads((self.root / "history.json").read_text(encoding="utf-8"))
        self.assertIn("example-story", history["topic_keys"])
        events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([event["platform"] for event in events], ["facebook", "instagram"])
        self.assertTrue(all(event["event"] == "published" for event in events))

    def test_instagram_waits_until_container_is_finished_before_publish(self):
        publisher = pipeline.MetaPublisher()
        publisher.ig_user_id = "ig-test-user"
        publisher.ig_token = "test-token"
        with patch.object(pipeline, "api_post", side_effect=[{"id": "container-1"}, {"id": "media-1"}]) as post:
            with patch.object(pipeline, "api_get", side_effect=[{"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}]) as get:
                with patch.object(pipeline.time, "sleep") as sleep:
                    result = publisher.publish_instagram_image(self.item)
        self.assertEqual(result, {"id": "media-1"})
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(pipeline.CONTAINER_STATUS_INTERVAL)
        self.assertEqual(post.call_args_list[1].args[0], "ig-test-user/media_publish")

    def test_instagram_carousel_waits_for_each_container_then_publishes_once(self):
        publisher = pipeline.MetaPublisher()
        publisher.ig_user_id = "ig-test-user"
        publisher.ig_token = "test-token"
        item = self.carousel_item()
        with patch.object(pipeline, "api_post", side_effect=[
            {"id": "child-1"}, {"id": "child-2"}, {"id": "carousel-1"}, {"id": "media-1"},
        ]) as post:
            with patch.object(pipeline, "api_get", return_value={"status_code": "FINISHED"}) as get:
                result = publisher.publish_instagram_carousel(item)
        self.assertEqual(result, {"id": "media-1"})
        self.assertEqual(get.call_count, 3)
        self.assertEqual(post.call_count, 4)
        self.assertEqual(post.call_args_list[2].args[1]["children"], "child-1,child-2")
        self.assertEqual(post.call_args_list[3].args[0], "ig-test-user/media_publish")

    def test_facebook_carousel_uploads_unpublished_slides_then_creates_one_post(self):
        publisher = pipeline.MetaPublisher()
        publisher.page_id = "page-1"
        publisher.page_token = "test-token"
        item = self.carousel_item()
        with patch.object(pipeline, "api_post", side_effect=[
            {"id": "photo-1"}, {"id": "photo-2"}, {"id": "post-1"},
        ]) as post:
            result = publisher.publish_facebook_carousel(item)
        self.assertEqual(result, {"id": "post-1"})
        self.assertEqual(post.call_args_list[0].args[1]["published"], "false")
        self.assertEqual(post.call_args_list[2].args[0], "page-1/feed")
        self.assertEqual(json.loads(post.call_args_list[2].args[1]["attached_media[0]"]), {"media_fbid": "photo-1"})
        self.assertEqual(json.loads(post.call_args_list[2].args[1]["attached_media[1]"]), {"media_fbid": "photo-2"})

    def test_instagram_does_not_publish_container_with_error_status(self):
        publisher = pipeline.MetaPublisher()
        publisher.ig_user_id = "ig-test-user"
        publisher.ig_token = "test-token"
        with patch.object(pipeline, "api_post", return_value={"id": "container-1"}) as post:
            with patch.object(pipeline, "api_get", return_value={"status_code": "ERROR"}):
                with self.assertRaisesRegex(RuntimeError, r"not publishable \(ERROR\)"):
                    publisher.publish_instagram_image(self.item)
        self.assertEqual(post.call_count, 1)

    def test_read_only_graph_request_keeps_token_out_of_url(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"status_code":"FINISHED"}'

        with patch.object(pipeline.urllib.request, "urlopen", return_value=Response()) as urlopen:
            result = pipeline.api_get("container-1", "private-test-token", {"fields": "status_code"})
        request = urlopen.call_args.args[0]
        self.assertNotIn("private-test-token", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer private-test-token")
        self.assertEqual(result["status_code"], "FINISHED")

    def test_instagram_does_not_publish_container_that_never_finishes(self):
        publisher = pipeline.MetaPublisher()
        publisher.ig_user_id = "ig-test-user"
        publisher.ig_token = "test-token"
        with patch.object(pipeline, "CONTAINER_STATUS_ATTEMPTS", 2):
            with patch.object(pipeline, "api_post", return_value={"id": "container-1"}) as post:
                with patch.object(pipeline, "api_get", return_value={"status_code": "IN_PROGRESS"}):
                    with patch.object(pipeline.time, "sleep"):
                        with self.assertRaisesRegex(RuntimeError, "did not finish processing"):
                            publisher.publish_instagram_image(self.item)
        self.assertEqual(post.call_count, 1)

    def test_staging_draft_adds_url_without_approval_or_publication(self):
        draft = json.loads(json.dumps(self.item))
        draft.pop("public_media_url")
        drafts = {"brand": {"required_image_size": [1080, 1350]}, "items": [draft]}
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": []}
        queue_path = self.root / "queue.json"
        log_path = self.root / "logs" / "events.jsonl"
        with patch.object(pipeline, "QUEUE_PATH", queue_path), patch.object(pipeline, "LOG_PATH", log_path):
            pipeline.stage_draft(drafts, queue, draft["id"], "https://media.example.com/post.png")
        staged = json.loads(queue_path.read_text(encoding="utf-8"))
        item = staged["items"][0]
        self.assertEqual(item["status"], "draft")
        self.assertNotIn("approval", item)
        self.assertEqual(item["public_media_url"], "https://media.example.com/post.png")
        with patch.object(pipeline, "MetaPublisher") as publisher:
            self.assertEqual(pipeline.publish_due(staged, execute=True, confirmation="FUNZUG"), 0)
            publisher.assert_not_called()

    def test_staging_carousel_draft_keeps_all_urls_and_stays_unapproved(self):
        draft = self.carousel_item()
        draft.pop("public_media_urls")
        drafts = {"brand": {"required_image_size": [1080, 1350]}, "items": [draft]}
        queue = {"brand": {"required_image_size": [1080, 1350]}, "items": []}
        urls = ["https://media.example.com/slide-1.png", "https://media.example.com/slide-2.png"]
        queue_path = self.root / "queue.json"
        log_path = self.root / "logs" / "events.jsonl"
        with patch.object(pipeline, "QUEUE_PATH", queue_path), patch.object(pipeline, "LOG_PATH", log_path):
            pipeline.stage_draft(drafts, queue, draft["id"], urls)
        staged = json.loads(queue_path.read_text(encoding="utf-8"))["items"][0]
        self.assertEqual(staged["public_media_urls"], urls)
        self.assertEqual(staged["status"], "draft")
        self.assertNotIn("approval", staged)


if __name__ == "__main__":
    unittest.main()
