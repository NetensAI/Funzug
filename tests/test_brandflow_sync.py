import base64
import json
import struct
import tempfile
import unittest
from pathlib import Path

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
            self.assertEqual(draft["scheduleTimezone"], "America/New_York")
            self.assertEqual(draft["claims"][0]["support_note"], "The cited source states this.")
            self.assertEqual(draft["sources"][0]["publisher"], "Example Institute")
            self.assertEqual(base64.b64decode(draft["image"]["data"]), image.read_bytes())

    def test_payload_rejects_non_image_or_external_asset_path(self):
        item = {"id": "bad", "format": "carousel", "media_path": "outside.png"}
        with self.assertRaisesRegex(ValueError, "single-image"):
            sync.payload_for(item)


if __name__ == "__main__":
    unittest.main()
