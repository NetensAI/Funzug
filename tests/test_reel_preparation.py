from pathlib import Path
import unittest
from unittest.mock import MagicMock

from scheduler.meta_browser import MetaBrowser, REEL_DATE
from scheduler.native_worker import NativeFailure


class ReelPreparationTests(unittest.TestCase):
    def setUp(self):
        self.browser=MetaBrowser(MagicMock(),Path('.'))
        for name in ('open_reel_composer','upload_reviewed_reel','set_reel_schedule','verify_schedule_fields'):
            setattr(self.browser,name,MagicMock())
        self.packet={'format':'reel','externalId':'reel-test','contentHash':'reviewed','caption':'Reviewed caption','platforms':['facebook','instagram'],'proposedSchedule':'2099-10-14T19:30:00+05:30'}
        self.controls={}
        def control(role,name,exact):
            if name not in self.controls:
                locator=MagicMock();locator.count.return_value=1
                locator.input_value.return_value=self.packet['caption']
                locator.is_checked.return_value=False
                locator.is_enabled.return_value=True
                locator.last.is_enabled.return_value=True
                self.controls[name]=locator
            return self.controls[name]
        self.browser.page.get_by_role.side_effect=control

    def test_unsent_wizard_stops_at_missing_acceptance_proof(self):
        with self.assertRaisesRegex(NativeFailure,'reel_final_proof_not_implemented'):
            self.browser.prepare(self.packet,[b'original'])
        self.browser.upload_reviewed_reel.assert_called_once_with(self.packet,[b'original'])
        self.controls['Next'].last.click.assert_called_once()
        self.controls['Next'].click.assert_called_once()
        self.browser.set_reel_schedule.assert_called_once_with(self.packet)
        self.browser.verify_schedule_fields.assert_called_once_with(self.packet,REEL_DATE)
        self.assertNotIn('Share',self.controls)
        self.assertNotIn('Schedule',self.controls)

    def test_changed_caption_cannot_advance_wizard(self):
        self.browser.page.get_by_role('textbox',name='Write into the dialogue box to include text with your post.',exact=True).input_value.return_value='Changed'
        with self.assertRaisesRegex(NativeFailure,'caption_entry_unconfirmed'):
            self.browser.prepare_reel(self.packet,[b'original'])
        self.browser.set_reel_schedule.assert_not_called()

    def test_upload_failure_cannot_advance_wizard(self):
        self.browser.upload_reviewed_reel.side_effect=NativeFailure('invalid_reviewed_media')
        with self.assertRaises(NativeFailure):self.browser.prepare_reel(self.packet,[b'wrong'])
        self.browser.set_reel_schedule.assert_not_called()
        self.assertEqual(self.controls,{})
