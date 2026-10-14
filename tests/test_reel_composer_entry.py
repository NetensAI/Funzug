import unittest
from pathlib import Path
from unittest.mock import MagicMock

from scheduler.meta_browser import MetaBrowser, PLANNER
from scheduler.native_worker import NativeFailure


class ReelComposerEntryTests(unittest.TestCase):
    def setUp(self):
        self.browser = MetaBrowser(MagicMock(), Path('.'))
        self.browser.visible = MagicMock()
        self.browser.select_platforms = MagicMock()
        self.controls = {}

        def control(role, name, exact):
            self.assertTrue(exact)
            key = (role, name)
            if key not in self.controls:
                locator = MagicMock()
                locator.count.return_value = 1
                locator.is_enabled.return_value = False
                locator.input_value.return_value = ''
                locator.evaluate.return_value = ''
                self.controls[key] = locator
            return self.controls[key]

        self.browser.page.get_by_role.side_effect = control

    def test_empty_wizard_navigation_does_not_upload_or_submit(self):
        self.browser.open_reel_composer(['facebook', 'instagram'])
        self.browser.page.goto.assert_called_once_with(PLANNER)
        self.assertEqual(self.browser.visible.call_count, 2)
        self.browser.select_platforms.assert_called_once_with(['facebook', 'instagram'])
        self.controls['button', 'Create'].click.assert_called_once()
        self.controls['menuitem', 'Create reel'].click.assert_called_once()
        for key in [('button', 'Add Video'), ('button', 'Next')]:
            self.controls[key].click.assert_not_called()

    def test_refuses_nonempty_wizard(self):
        self.browser.open_reel_composer(['instagram'])
        self.controls['button', 'Next'].is_enabled.return_value = True
        with self.assertRaisesRegex(NativeFailure, 'reel_composer_not_empty'):
            self.browser.open_reel_composer(['instagram'])

    def test_refuses_changed_upload_control(self):
        self.browser.open_reel_composer(['facebook'])
        self.controls['button', 'Add Video'].count.return_value = 0
        with self.assertRaisesRegex(NativeFailure, 'reel_composer_changed'):
            self.browser.open_reel_composer(['facebook'])
