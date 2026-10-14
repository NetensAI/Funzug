from pathlib import Path
import unittest
from unittest.mock import MagicMock

from scheduler.meta_browser import MetaBrowser
from scheduler.native_worker import NativeFailure


class MixedPlannerGateTests(unittest.TestCase):
    def test_publication_cannot_be_inferred_from_caption_only_for_mixed_media(self):
        browser=MetaBrowser(MagicMock(),Path('.'))
        for media_format in ('carousel','reel'):
            with self.assertRaisesRegex(NativeFailure,'mixed_publication_media_not_verified'):
                browser.inspect_publication({'format':media_format})
        browser.planner.goto.assert_not_called()
