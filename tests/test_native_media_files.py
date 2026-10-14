import hashlib
from pathlib import Path
import tempfile
import unittest

from scheduler.native_media_files import stage_reviewed_media
from scheduler.native_worker import NativeFailure


class NativeMediaFilesTests(unittest.TestCase):
    def test_order_original_bytes_and_cleanup_after_interruption(self):
        packet={'format':'carousel','media':[{'mimeType':'image/png'},{'mimeType':'image/jpeg'}]}
        blobs=[b'first original bytes',b'second original bytes']
        with tempfile.TemporaryDirectory() as root:
            paths=[]
            with self.assertRaisesRegex(RuntimeError,'interrupted'):
                with stage_reviewed_media(packet,blobs,root) as (paths,hashes):
                    self.assertEqual([p.name for p in paths],['00.png','01.jpg'])
                    self.assertEqual([p.read_bytes() for p in paths],blobs)
                    self.assertEqual(hashes,[hashlib.sha256(b).hexdigest() for b in blobs])
                    raise RuntimeError('interrupted')
            self.assertTrue(all(not p.exists() for p in paths))
            self.assertEqual(list(Path(root).iterdir()),[])

    def test_video_keeps_mp4_and_image_keeps_legacy_single_file(self):
        with tempfile.TemporaryDirectory() as root:
            for packet,assets,suffix in [({'format':'reel','media':[{'mimeType':'video/mp4'}]},[b'original mp4'],'.mp4'),({'image':{'mimeType':'image/png'}},b'original png','.png')]:
                with stage_reviewed_media(packet,assets,root) as (paths,hashes):
                    self.assertEqual(len(paths),1)
                    self.assertEqual(paths[0].suffix,suffix)

    def test_invalid_manifest_never_creates_files(self):
        with tempfile.TemporaryDirectory() as root:
            for packet,assets in [({'format':'carousel','media':[]},[]),({'format':'reel','media':[{'mimeType':'image/png'}]},[b'wrong']),({'image':{'mimeType':'video/mp4'}},b'wrong')]:
                with self.assertRaises(NativeFailure):
                    with stage_reviewed_media(packet,assets,root):
                        self.fail('Invalid media was staged')
            self.assertEqual(list(Path(root).iterdir()),[])
