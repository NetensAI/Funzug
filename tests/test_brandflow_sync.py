import base64
import json
import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.brandflow_sync as sync


class BrandFlowPayloadTests(unittest.TestCase):
    def test_ingest_secret_trims_surrounding_whitespace(self):
        with patch.dict("os.environ", {"FUNZUG_DRAFT_INGEST_SECRET": "  " + "s" * 64 + "\r\n"}):
            self.assertEqual(sync.secret(), "s" * 64)

    def test_ingest_secret_rejects_internal_control_characters_without_echoing_them(self):
        with patch.dict("os.environ", {"FUNZUG_DRAFT_INGEST_SECRET": "s" * 32 + "\n" + "t" * 32}):
            with self.assertRaisesRegex(RuntimeError, "contains invalid characters") as raised:
                sync.secret()
            self.assertNotIn("s" * 32, str(raised.exception))

    def test_cli_entrypoint_imports_pipeline_from_scripts_directory(self):
        result = subprocess.run(
            [sys.executable, str(sync.ROOT / "scripts" / "brandflow_sync.py"), "--help"],
            cwd=sync.ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("{sync,process-approvals,sync-results}", result.stdout)

    def test_payload_preserves_claim_support_and_source_metadata(self):
        with tempfile.TemporaryDirectory(dir=sync.ROOT) as directory:
            root = Path(directory)
            image = root / "post.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 1080, 1350) + b"\x08\x06\x00\x00\x00")
            item = {
                "id": "funzug-example-1",
                "format": "image",
                "headline": "Example",
                "caption": "Caption",
                "media_path": str(image.relative_to(sync.ROOT)),
                "scheduled_at": "2026-11-06T22:30:00+05:30",
                "platforms": ["facebook", "instagram"],
                "claims": [{"text": "Fact", "source_ids": ["src-1"], "support_note": "The cited source states this."}],
                "sources": [{"id": "src-1", "title": "Primary source", "publisher": "Example Institute", "url": "https://example.org/report", "published_at": "2026-10-01T00:00:00Z", "checked_at": "2026-10-11T00:00:00Z"}],
            }
            payload = sync.payload_for(item)
            draft = payload["drafts"][0]
            self.assertEqual(payload["brandSlug"], "funzug")
            self.assertEqual(draft["scheduleTimezone"], "Asia/Kolkata")
            self.assertEqual(draft["proposedSchedule"], "2026-11-06T22:30:00+05:30")
            self.assertEqual(draft["claims"][0]["support_note"], "The cited source states this.")
            self.assertEqual(draft["sources"][0]["publisher"], "Example Institute")
            self.assertEqual(base64.b64decode(draft["image"]["data"]), image.read_bytes())

    def test_payload_rejects_non_image_or_external_asset_path(self):
        item = {"id": "bad", "format": "carousel", "media_path": "outside.png"}
        with self.assertRaisesRegex(ValueError, "single-image"):
            sync.payload_for(item)

    def test_approval_uses_brandflow_selected_ist_schedule(self):
        item = {"id": "funzug-example-1", "status": "draft", "scheduled_at": "2026-11-06T22:30:00+05:30"}
        drafts = {"items": [item]}
        queue = {"items": []}
        status = {
            "status": "approved",
            "publicationAuthorized": True,
            "reviewChecks": {},
            "scheduleTimezone": "Asia/Kolkata",
            "proposedSchedule": "2026-11-12T19:15:00+05:30",
            "reviewedBy": "vatsal",
            "reviewNote": "Approved for scheduled publishing at Nov 12, 2026, 7:15 PM IST",
            "reviewedAt": "2026-11-12T12:00:00Z",
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api"),
            patch.object(sync, "api_status", return_value={item["id"]: status}),
            patch.object(sync.pipeline, "load_json", side_effect=[drafts, queue, queue]),
            patch.object(sync.pipeline, "host_and_approve_draft") as process,
        ):
            sync.process_approvals()
        passed_drafts = process.call_args.args[0]
        self.assertEqual(passed_drafts["items"][0]["scheduled_at"], "2026-11-12T19:15:00+05:30")
        self.assertEqual(process.call_args.args[5], {"approvalConfirmed": True})

    def test_expired_approval_is_skipped_without_blocking_future_approval(self):
        expired = {"id": "funzug-example-past", "status": "draft", "scheduled_at": "2026-11-06T22:30:00+05:30"}
        future = {"id": "funzug-example-future", "status": "draft", "scheduled_at": "2026-11-06T22:30:00+05:30"}
        drafts = {"items": [expired, future]}
        queue = {"items": []}
        expired_status = {
            "status": "approved",
            "publicationAuthorized": True,
            "reviewChecks": {"approvalConfirmed": True},
            "scheduleTimezone": "Asia/Kolkata",
            "proposedSchedule": "2000-01-01T19:15:00+05:30",
            "reviewedBy": "vatsal",
            "reviewNote": "Approved for scheduled publishing",
            "reviewedAt": "2000-01-01T12:00:00Z",
        }
        future_status = {
            **expired_status,
            "proposedSchedule": "2999-01-01T19:15:00+05:30",
            "reviewedAt": "2998-12-31T12:00:00Z",
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api"),
            patch.object(sync, "api_status", return_value={
                expired["id"]: expired_status,
                future["id"]: future_status,
            }),
            patch.object(sync.pipeline, "load_json", side_effect=[drafts, queue, queue]),
            patch.object(sync.pipeline, "host_and_approve_draft") as process,
        ):
            self.assertEqual(sync.process_approvals(), 0)
        self.assertEqual(process.call_count, 1)
        self.assertEqual(process.call_args.args[2], future["id"])

    def test_published_item_does_not_block_later_approvals(self):
        published = {"id": "already-posted", "status": "published"}
        queue = {"items": [published]}
        status = {
            "status": "approved", "publicationAuthorized": True,
            "scheduleTimezone": "Asia/Kolkata",
            "proposedSchedule": "2999-01-01T19:15:00+05:30",
            "reviewedBy": "vatsal", "reviewNote": "Original approval",
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api"),
            patch.object(sync, "api_status", return_value={published["id"]: status}),
            patch.object(sync.pipeline, "load_json", side_effect=[{"items": []}, queue]),
            patch.object(sync.pipeline, "host_and_approve_draft") as upload,
        ):
            self.assertEqual(sync.process_approvals(), 0)
        upload.assert_not_called()

    def test_sync_results_sends_only_fully_published_posts(self):
        completed = {
            "id": "published-example", "status": "published",
            "platforms": ["facebook", "instagram"],
            "platform_results": {
                "facebook": {"status": "published", "post_id": "page_post", "published_at": "2026-10-11T17:00:00Z"},
                "instagram": {"status": "published", "post_id": "ig_post", "published_at": "2026-10-11T16:00:00Z"},
            },
        }
        with (
            patch.object(sync, "secret", return_value="s" * 64),
            patch.object(sync, "api_url", return_value="https://example.test/api/integrations/funzug/drafts"),
            patch.object(sync.pipeline, "load_json", side_effect=[{"items": [{"id": completed["id"]}]}, {"items": [completed, {"id": "other", "status": "approved"}]}]),
            patch.object(sync, "api_request", return_value={}) as request,
        ):
            self.assertEqual(sync.sync_results(), 0)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[1], "https://example.test/api/integrations/funzug/publications")
        payload = request.call_args.args[3]
        self.assertEqual(payload["externalId"], completed["id"])
        self.assertEqual(set(payload["platformResults"]), {"facebook", "instagram"})


if __name__ == "__main__":
    unittest.main()
