import base64
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.brandflow_sync as sync


class BrandFlowPayloadTests(unittest.TestCase):
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
                "scheduled_at": "2026-11-06T12:00:00-05:00",
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
            "reviewChecks": {"approvalConfirmed": True},
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


if __name__ == "__main__":
    unittest.main()
