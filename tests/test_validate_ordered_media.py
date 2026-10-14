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
from unittest.mock import patch
from scripts.validate_ordered_media import validate_ordered_media, verify_video_metadata, probe_video_asset


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
            self.assertEqual(probe_video_asset(path),draft['media'][0])
            draft['media'][0]['durationMs'] = 2000
            with self.assertRaisesRegex(ValueError,'duration differs'):
                validate_ordered_media(draft)

    def test_real_reel_draft_validation_and_sync(self):
        if not (shutil.which('ffmpeg') and shutil.which('ffprobe')):
            if os.environ.get('FUNZUG_REQUIRE_MEDIA_DECODER_TESTS')=='1':self.fail('Real decoders required')
            self.skipTest('FFmpeg is not installed locally')
        import funzug_pipeline as pipeline
        import scripts.brandflow_sync as sync
        with tempfile.TemporaryDirectory(prefix='funzug-reel-sync-') as directory:
            path=Path(directory)/'fixture.mp4'
            subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','color=c=blue:s=40x50:r=10','-t','1','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True,capture_output=True,timeout=30)
            item=dict(id='reel-draft',format='reel',media_path='fixture.mp4',headline='Headline',caption='Caption',topic_key='reel-fixture',scheduled_at='2099-01-01T12:00:00+05:30',platforms=['facebook','instagram'],claims=[dict(text='Claim',source_ids=['primary'],support_note='Source establishes this claim')],sources=[dict(id='primary',title='Source',publisher='Institute',url='https://example.org/source',published_at=None,checked_at='2026-10-13T12:00:00+05:30')])
            with patch.object(pipeline,'ROOT',Path(directory)),patch.object(sync,'ROOT',Path(directory)):
                self.assertEqual(pipeline.validate_item(item,(1080,1350),require_public_media_url=False),[])
                self.assertTrue(any('Reel delivery is not enabled' in e for e in pipeline.validate_item(item,(1080,1350))))
                packet=sync.payload_for(item);self.assertEqual(packet['schemaVersion'],2)
                media=packet['drafts'][0]['media'][0]
                self.assertEqual((media['width'],media['height'],media['durationMs']),(40,50,1000))
                self.assertEqual(base64.b64decode(media['data']),path.read_bytes())

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
