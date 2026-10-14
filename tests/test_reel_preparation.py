from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import hashlib

from scheduler.meta_browser import MetaBrowser, REEL_DATE
from scheduler.native_worker import NativeFailure, binding, verify_proof


class ReelPreparationTests(unittest.TestCase):
    def setUp(self):
        self.browser=MetaBrowser(MagicMock(),Path('.'))
        for name in ('open_reel_composer','upload_reviewed_reel','set_reel_schedule','verify_schedule_fields','prepared_reel'):
            setattr(self.browser,name,MagicMock())
        self.packet={'format':'reel','externalId':'reel-test','contentHash':'reviewed','caption':'Reviewed caption','platforms':['facebook','instagram'],'proposedSchedule':'2099-10-14T19:30:00+05:30'}
        self.controls={}
        def control(role,name,exact):
            if name not in self.controls:
                locator=MagicMock();locator.count.return_value=1
                locator.input_value.return_value=self.packet['caption']
                locator.evaluate.return_value=self.packet['caption']
                locator.is_checked.return_value=False
                locator.is_enabled.return_value=True
                locator.last.is_enabled.return_value=True
                self.controls[name]=locator
            return self.controls[name]
        self.browser.page.get_by_role.side_effect=control

    def test_unsent_wizard_requires_separate_live_acceptance_proof(self):
        self.browser.prepared_reel.return_value={'fixture':'proof'}
        self.assertEqual(self.browser.prepare(self.packet,[b'original']),{'fixture':'proof'})
        self.browser.prepared_reel.assert_called_once_with(self.packet)
        self.browser.upload_reviewed_reel.assert_called_once_with(self.packet,[b'original'])
        self.controls['Next'].last.click.assert_called_once()
        self.controls['Next'].click.assert_called_once()
        self.browser.set_reel_schedule.assert_called_once_with(self.packet)
        self.browser.verify_schedule_fields.assert_called_once_with(self.packet,REEL_DATE)
        self.assertNotIn('Share',self.controls)
        self.assertNotIn('Schedule',self.controls)

    def test_changed_caption_cannot_advance_wizard(self):
        self.browser.page.get_by_role('textbox',name='Write into the dialogue box to include text with your post.',exact=True).evaluate.return_value='Changed'
        with self.assertRaisesRegex(NativeFailure,'caption_entry_unconfirmed'):
            self.browser.prepare_reel(self.packet,[b'original'])
        self.browser.set_reel_schedule.assert_not_called()

    def test_upload_failure_cannot_advance_wizard(self):
        self.browser.upload_reviewed_reel.side_effect=NativeFailure('invalid_reviewed_media')
        with self.assertRaises(NativeFailure):self.browser.prepare_reel(self.packet,[b'wrong'])
        self.browser.set_reel_schedule.assert_not_called()
        self.assertEqual(self.controls,{})

    def test_live_final_proof_and_option_changes(self):
        browser=MetaBrowser(MagicMock(),Path('.'))
        packet={**self.packet,'media':[{'width':720,'height':900,'durationMs':5000}]}
        assets=[b'original MP4']
        browser.item_binding=binding(packet)
        browser.reel_upload_binding={**binding(packet),'filename':'00.mp4','sha256':hashlib.sha256(assets[0]).hexdigest()}
        browser.visible=MagicMock();browser.selected_platforms=MagicMock(return_value=packet['platforms'])
        browser.read_caption_editor=MagicMock(return_value=packet['caption'])
        browser.reel_submit_control=MagicMock();browser.verify_schedule_fields=MagicMock()
        control=browser.page.get_by_role.return_value
        control.count.return_value=1;control.is_checked.return_value=False;control.last.is_enabled.return_value=True
        text=browser.page.get_by_text.return_value
        text.count.return_value=1;text.inner_text.return_value='Reels · 5 seconds ·'
        with patch('scheduler.meta_browser.verify_ordered_package',return_value=assets):
            proof=browser.prepared_reel(packet)
            verify_proof(packet,proof,assets)
            self.assertEqual(browser.submission_format,'reel')
            browser.reel_submit_control.return_value.click.assert_not_called()
            control.is_checked.return_value=True
            with self.assertRaisesRegex(NativeFailure,'unexpected_composer_option'):
                browser.prepared_reel(packet)
            self.assertIsNone(browser.submission_format)

    def test_submit_refuses_unverified_composer(self):
        browser=MetaBrowser(MagicMock(),Path('.'))
        with self.assertRaisesRegex(NativeFailure,'composer_not_verified'):browser.submit()
        browser.page.get_by_role.assert_not_called()
