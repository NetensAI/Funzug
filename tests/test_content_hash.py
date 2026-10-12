import base64
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import scripts.brandflow_sync as sync


class ContentHashTests(unittest.TestCase):
    def payload(self):
        return {'drafts': [{'headline': 'Mars', 'caption': 'Blue “light” 🌍', 'claims': [{'text': 'claim', 'source_ids': ['a'], 'support_note': 'note'}], 'sources': [{'id': 'a', 'checked_at': '2026-10-12T11:00:00+05:30'}], 'platforms': ['facebook', 'instagram'], 'image': {'mimeType': 'image/png', 'data': base64.b64encode(b'image-bytes').decode()}}]}

    def test_caption_image_and_claim_changes_invalidate_hash(self):
        payload = self.payload()
        with patch.object(sync, 'payload_for', return_value=payload):
            original = sync.approval_content_hash({})
            for key, value in [('caption', 'changed'), ('claims', []), ('platforms', ['instagram'])]:
                old = payload['drafts'][0][key]
                payload['drafts'][0][key] = value
                self.assertNotEqual(original, sync.approval_content_hash({}))
                payload['drafts'][0][key] = old
            payload['drafts'][0]['image']['data'] = base64.b64encode(b'changed').decode()
            self.assertNotEqual(original, sync.approval_content_hash({}))

    def test_missing_or_mismatched_hash_fails_closed(self):
        with patch.object(sync, 'approval_content_hash', return_value='a'*64):
            for status in [{}, {'contentHash': 'b'*64}, {'contentHash': None}]:
                with self.assertRaisesRegex(RuntimeError, 'does not match'):
                    sync.require_matching_approved_content({'id': 'draft'}, status)
            sync.require_matching_approved_content({'id': 'draft'}, {'contentHash': 'a'*64})

    def test_missing_fingerprint_blocks_before_public_upload_or_queue_write(self):
        item = {'id': 'draft', 'status': 'draft', 'scheduled_at': '2999-01-01T19:30:00+05:30'}
        status = {'status': 'approved', 'publicationAuthorized': True, 'scheduleTimezone': 'Asia/Kolkata', 'reviewedBy': 'owner', 'reviewNote': 'Approved', 'proposedSchedule': item['scheduled_at']}
        with patch.object(sync, 'secret', return_value='unused'), patch.object(sync, 'api_url', return_value='https://example.invalid'), patch.object(sync, 'api_status', return_value={'draft': status}), patch.object(sync.pipeline, 'load_json', side_effect=[{'items': [item]}, {'items': []}]), patch.object(sync.pipeline, 'host_and_approve_draft') as upload, patch.object(sync.pipeline, 'save_json') as write:
            with self.assertRaisesRegex(RuntimeError, 'does not match'):
                sync.process_approvals()
            upload.assert_not_called()
            write.assert_not_called()

    def test_python_and_dashboard_hashes_match_for_unicode_and_nested_metadata(self):
        node = shutil.which('node')
        if not node:
            candidate = Path('C:/Program Files/nodejs/node.exe')
            node = str(candidate) if candidate.is_file() else None
        if not node:
            self.skipTest('Node runtime required for cross-language test')
        payload = self.payload()['drafts'][0]
        script = "import {draftContentHash} from './brandflow/lib/funzug-content-hash.mjs'; let s='';for await(const c of process.stdin)s+=c;const d=JSON.parse(s);console.log(draftContentHash({headline:d.headline,caption:d.caption,claims:d.claims,evidence_sources:d.sources,platforms:d.platforms,image_mime_type:d.image.mimeType,image_bytes:Buffer.from(d.image.data,'base64')}));"
        result = subprocess.run([node, '--input-type=module', '-e', script], input=json.dumps(payload), text=True, capture_output=True, cwd=sync.ROOT, check=True)
        with patch.object(sync, 'payload_for', return_value={'drafts': [payload]}):
            self.assertEqual(result.stdout.strip(), sync.approval_content_hash({}))
