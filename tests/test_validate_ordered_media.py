import base64
import copy
import io
import unittest
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from PIL import Image
from scripts.validate_ordered_media import validate_ordered_media, verify_video_metadata


class OrderedMediaDecodeTests(unittest.TestCase):
    def test_actual_mp4_decoding(self):
        available = shutil.which('ffmpeg') and shutil.which('ffprobe')
        if not available:
            if os.environ.get('FUNZUG_REQUIRE_MEDIA_DECODER_TESTS') == '1':
                self.fail('Real media decoders are required in CI')
            self.skipTest('FFmpeg is not installed locally')
        with tempfile.TemporaryDirectory(prefix='funzug-reel-fixture-') as directory:
            path = Path(directory) / 'fixture.mp4'
            subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','color=c=blue:s=40x50:r=10','-t','1','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True,timeout=30)
            draft = self.fixture(); draft['format'] = 'reel'
            draft['media'] = [dict(mimeType='video/mp4',width=40,height=50,durationMs=1000,data=base64.b64encode(path.read_bytes()).decode())]
            self.assertEqual(len(validate_ordered_media(draft)),64)
            draft['media'][0]['durationMs'] = 2000
            with self.assertRaisesRegex(ValueError,'duration differs'):
                validate_ordered_media(draft)

    def fixture(self):
        assets = []
        for color in ('red', 'blue'):
            buffer = io.BytesIO()
            Image.new('RGB', (40, 50), color).save(buffer, format='PNG')
            assets.append(dict(mimeType='image/png', width=40, height=50, data=base64.b64encode(buffer.getvalue()).decode()))
        return dict(format='carousel', headline='Headline', caption='Caption', claims=[], sources=[], platforms=['facebook'], media=assets)

    def test_valid_images_are_decoded_without_mutation(self):
        draft = self.fixture()
        before = copy.deepcopy(draft)
        self.assertEqual(len(validate_ordered_media(draft)), 64)
        self.assertEqual(draft, before)

    def test_header_only_truncated_and_metadata_mismatch_fail(self):
        for mode in ('truncated', 'dimensions', 'mime'):
            draft = self.fixture()
            asset = draft['media'][0]
            if mode == 'truncated':
                asset['data'] = base64.b64encode(base64.b64decode(asset['data'])[:24]).decode()
            elif mode == 'dimensions':
                asset.update(width=80, height=100)
            else:
                asset['mimeType'] = 'image/jpeg'
            with self.assertRaises((ValueError, OSError)):
                validate_ordered_media(draft)

    def video(self):
        return dict(streams=[dict(codec_type='video',codec_name='h264',pix_fmt='yuv420p',width=40,height=50,sample_aspect_ratio='1:1',avg_frame_rate='30/1')],format=dict(duration='1.0',format_name='mov,mp4,m4a,3gp,3g2,mj2'))

    def test_video_metadata_rejects_rotation_duration_codec_and_streams(self):
        asset = dict(width=40,height=50,durationMs=1000)
        verify_video_metadata(self.video(), asset)
        for mutation in (
            lambda x: x['streams'][0].update(tags={'rotate':'90'}),
            lambda x: x['streams'][0].update(codec_name='hevc'),
            lambda x: x['streams'][0].update(avg_frame_rate='0/0'),
            lambda x: x['format'].update(duration='nan'),
            lambda x: x['format'].update(duration='2'),
            lambda x: x['streams'].append({'codec_type':'subtitle'}),
        ):
            info = self.video(); mutation(info)
            with self.assertRaises(ValueError):
                verify_video_metadata(info, asset)

    def test_missing_decoder_fails_closed(self):
        draft = self.fixture(); draft['format'] = 'reel'
        draft['media'] = [dict(mimeType='video/mp4',width=40,height=50,durationMs=1000,data=base64.b64encode(b'not video').decode())]
        with self.assertRaisesRegex(ValueError, 'decoder unavailable'):
            validate_ordered_media(draft, ffprobe='funzug-nonexistent-decoder')
