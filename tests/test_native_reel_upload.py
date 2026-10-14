import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scheduler.meta_browser import MetaBrowser
from scheduler.native_worker import NativeFailure


class NativeReelUploadTests(unittest.TestCase):
    def fixture(self):
        return {'format':'reel','media':[{'mimeType':'video/mp4','width':320,'height':400,'durationMs':3000}],
                'externalId':'test-reel','contentHash':'reviewed','proposedSchedule':'2099-10-14T19:00:00+05:30','platforms':['facebook','instagram']}

    def test_original_video_cleanup_and_binding_without_navigation(self):
        packet=self.fixture();assets=[b'original MP4 fixture bytes']
        with tempfile.TemporaryDirectory() as root:
            browser=MetaBrowser(MagicMock(),Path(root));browser.visible=MagicMock()
            delete=MagicMock();delete.count.side_effect=[0,1]
            add=MagicMock()
            browser.page.get_by_role.side_effect=lambda role,name,exact:delete if name=='Delete' else add
            chooser=MagicMock();browser.page.expect_file_chooser.return_value.__enter__.return_value.value=chooser
            files=[]
            def set_file(path):
                files.append(Path(path));self.assertEqual(Path(path).read_bytes(),assets[0])
            chooser.set_files.side_effect=set_file
            with patch('scheduler.meta_browser.verify_ordered_package',return_value=assets) as verify:
                result=browser.upload_reviewed_reel(packet,assets)
            verify.assert_called_once_with(packet)
            self.assertEqual(result['sha256'],hashlib.sha256(assets[0]).hexdigest())
            self.assertEqual(result['durationMs'],3000)
            browser.page.get_by_text.assert_any_call('320 x 400',exact=True)
            self.assertTrue(all(not path.exists() for path in files))
            browser.page.goto.assert_not_called()
            self.assertEqual(add.click.call_count,1)

    def test_invalid_or_changed_bytes_never_open_upload(self):
        browser=MetaBrowser(MagicMock(),Path('.'));packet=self.fixture()
        with patch('scheduler.meta_browser.verify_ordered_package',return_value=[b'original']):
            with self.assertRaisesRegex(NativeFailure,'reviewed_media_file_changed'):
                browser.upload_reviewed_reel(packet,[b'changed'])
        with patch('scheduler.meta_browser.verify_ordered_package',side_effect=NativeFailure('invalid_reviewed_media')):
            with self.assertRaises(NativeFailure):browser.upload_reviewed_reel(packet,[b'original'])
        browser.page.expect_file_chooser.assert_not_called()
