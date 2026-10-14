import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from scheduler.meta_browser import MetaBrowser
from scheduler.native_worker import NativeFailure, verify_ordered_package
from tests import test_native_ordered_package as ordered_fixtures


class NativeImageUploadTests(unittest.TestCase):
    def test_uploads_original_slides_sequentially_and_removes_local_files(self):
        packet=ordered_fixtures.NativeOrderedPackageTests().fixture()
        assets=verify_ordered_package(packet)
        with tempfile.TemporaryDirectory() as root:
            browser=MetaBrowser(MagicMock(),Path(root))
            remove=MagicMock();remove.count.side_effect=[0,1,2]
            urls=['https://scontent.example.fbcdn.net/first.jpg','https://scontent.example.fbcdn.net/second.jpg']
            remove.evaluate_all.side_effect=[urls[:1],urls]
            add=MagicMock()
            browser.page.get_by_role.side_effect=lambda role,name,exact: remove if name=='Remove photo' else add
            chooser=MagicMock();browser.page.expect_file_chooser.return_value.__enter__.return_value.value=chooser
            uploaded=[];paths=[]
            def select(path):
                paths.append(Path(path));uploaded.append(Path(path).read_bytes())
            chooser.set_files.side_effect=select
            hashes=browser.upload_reviewed_images(packet,assets)
            self.assertEqual(uploaded,assets)
            self.assertEqual(hashes,[hashlib.sha256(asset).hexdigest() for asset in assets])
            self.assertEqual(add.click.call_count,2)
            self.assertEqual(browser.uploaded_thumbnail_urls,tuple(urls))
            self.assertTrue(all(not p.exists() for p in paths))
            self.assertEqual(list(Path(root).iterdir()),[])

    def test_changed_bytes_cannot_open_file_chooser(self):
        packet=ordered_fixtures.NativeOrderedPackageTests().fixture()
        browser=MetaBrowser(MagicMock(),Path('.'))
        with self.assertRaisesRegex(NativeFailure,'reviewed_media_file_changed'):
            browser.upload_reviewed_images(packet,[b'changed',b'changed'])
        browser.page.expect_file_chooser.assert_not_called()

    def test_existing_media_cannot_be_appended_to(self):
        packet=ordered_fixtures.NativeOrderedPackageTests().fixture()
        browser=MetaBrowser(MagicMock(),Path('.'))
        browser.page.get_by_role.return_value.count.return_value=1
        with self.assertRaisesRegex(NativeFailure,'composer_not_empty'):
            browser.upload_reviewed_images(packet,verify_ordered_package(packet))
        browser.page.expect_file_chooser.assert_not_called()

    def test_reordered_thumbnail_cannot_pass_pre_submit_check(self):
        browser=MetaBrowser(MagicMock(),Path('.'))
        urls=['https://scontent.example.fbcdn.net/first.jpg','https://scontent.example.fbcdn.net/second.jpg']
        browser.uploaded_thumbnail_urls=tuple(urls)
        locator=browser.page.get_by_role.return_value
        locator.evaluate_all.return_value=urls
        browser.verify_carousel_upload_order(2)
        locator.evaluate_all.return_value=list(reversed(urls))
        with self.assertRaisesRegex(NativeFailure,'uploaded_media_order_changed'):
            browser.verify_carousel_upload_order(2)

    def test_untrusted_or_ambiguous_thumbnail_sources_fail_closed(self):
        browser=MetaBrowser(MagicMock(),Path('.'))
        for urls in ([None],['https://other.example/a.jpg'],['https://fbcdn.net.attacker.example/a.jpg'],['https://scontent.example.fbcdn.net/a.jpg']*2,[]):
            browser.page.get_by_role.return_value.evaluate_all.return_value=urls
            with self.assertRaisesRegex(NativeFailure,'carousel_thumbnails_unconfirmed'):
                browser.carousel_thumbnail_urls()
