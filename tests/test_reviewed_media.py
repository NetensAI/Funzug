import base64
import copy
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from scripts.reviewed_media import approval_fingerprint

ROOT = Path(__file__).resolve().parents[1]


class ReviewedMediaTests(unittest.TestCase):
    def fixture(self, kind='carousel'):
        assets = [{'mimeType': 'image/png', 'width': 1122, 'height': 1402,
                   'data': base64.b64encode(value).decode()} for value in (b'first', b'second')]
        if kind == 'reel':
            assets = [{**assets[0], 'mimeType': 'video/mp4', 'durationMs': 30000}]
        return dict(headline='Reviewed 🌍', caption='Caption', claims=[{'text': 'Claim'}],
                    sources=[{'id': 'primary'}], platforms=['facebook', 'instagram'], format=kind, media=assets)

    def test_order_bytes_metadata_and_format_are_bound(self):
        original = self.fixture()
        digest = approval_fingerprint(original)
        changes = []
        swapped = copy.deepcopy(original)
        swapped['media'].reverse()
        changes.append(swapped)
        for key, value in [('data', base64.b64encode(b'changed').decode()),
                           ('mimeType', 'image/jpeg'), ('width', 1080)]:
            changed = copy.deepcopy(original)
            changed['media'][0][key] = value
            if key == 'width':
                changed['media'][0]['height'] = 1350
            changes.append(changed)
        for changed in changes:
            self.assertNotEqual(digest, approval_fingerprint(changed))
        reel = self.fixture('reel')
        before = approval_fingerprint(reel)
        reel['media'][0]['durationMs'] += 1
        self.assertNotEqual(before, approval_fingerprint(reel))

    def test_invalid_media_fails_closed(self):
        for key, value in [('width', True), ('height', 1122), ('mimeType', 'text/plain'),
                           ('data', 'not base64'), ('data', '')]:
            packet = self.fixture()
            packet['media'][0][key] = value
            with self.assertRaises(ValueError):
                approval_fingerprint(packet)
        for assets in ([], self.fixture()['media'][:1], self.fixture()['media'] * 6):
            with self.assertRaises(ValueError):
                approval_fingerprint({**self.fixture(), 'media': assets})
        packet = self.fixture()
        packet['media'][1] = packet['media'][0].copy()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            approval_fingerprint(packet)
        packet = self.fixture('reel')
        packet['media'][0]['durationMs'] = 0
        with self.assertRaises(ValueError):
            approval_fingerprint(packet)

    def test_python_dashboard_parity_and_legacy_image_compatibility(self):
        node = shutil.which('node') or 'C:/Program Files/nodejs/node.exe'
        if not Path(node).is_file():
            self.skipTest('Node unavailable')
        script = "import {reviewedMediaHash} from './brandflow/lib/funzug-content-hash.mjs'; let s='';for await(const c of process.stdin)s+=c;console.log(reviewedMediaHash(JSON.parse(s)));"
        image = self.fixture()
        image.pop('format')
        image['image'] = image.pop('media')[0]
        for draft in (self.fixture(), self.fixture('reel'), image):
            result = subprocess.run([node, '--input-type=module', '-e', script], input=json.dumps(draft),
                                    text=True, capture_output=True, cwd=ROOT, check=True)
            self.assertEqual(result.stdout.strip(), approval_fingerprint(draft))

    def test_native_worker_rejects_new_formats_until_delivery_is_implemented(self):
        from scheduler.native_worker import verify_package, NativeFailure
        for packet in ({'format': 'carousel'}, {'format': 'reel'}, {'media': []}):
            with self.assertRaisesRegex(NativeFailure, 'unsupported_native_media_format'):
                verify_package(packet)
