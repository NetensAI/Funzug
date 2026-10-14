import unittest
from scheduler.meta_browser import verify_reel_duration_label
from scheduler.native_worker import NativeFailure


class ReelDurationLabelTests(unittest.TestCase):
    def test_observed_label_and_whole_second_display_precision(self):
        verify_reel_duration_label('Reels · 5 seconds ·',5000)
        verify_reel_duration_label('Reels · 5 seconds',5200)

    def test_loading_unknown_units_and_mismatches_fail_closed(self):
        for label,value in [('Reels · Loading... ·',5000),('Reels · 5 minutes',5000),('Reels · 5 seconds',6000),('Reels · 5 seconds',True),('Reels · 0 seconds',1000),('Other · 5 seconds',5000),('Reels · 181 seconds',181000)]:
            with self.assertRaisesRegex(NativeFailure,'reel_duration_unconfirmed'):
                verify_reel_duration_label(label,value)
