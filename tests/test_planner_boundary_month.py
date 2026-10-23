import datetime as dt
import unittest
from scheduler.meta_browser import planner_month_pattern
from scheduler.native_worker import IST

class BoundaryMonthTests(unittest.TestCase):
    def test_october_last_week_accepts_observed_range(self):
        for day in range(25,32):
            pattern=planner_month_pattern(dt.datetime(2026,10,day,tzinfo=IST))
            self.assertIsNotNone(pattern.fullmatch('Oct - Nov'))
            self.assertIsNotNone(pattern.fullmatch('October'))
            for label in ('November','Sep - Oct','Oct - Dec','October extra'):
                self.assertIsNone(pattern.fullmatch(label))

    def test_previous_week_does_not_accept_wrong_range(self):
        pattern=planner_month_pattern(dt.datetime(2026,10,24,tzinfo=IST))
        self.assertIsNotNone(pattern.fullmatch('October'))
        self.assertIsNone(pattern.fullmatch('Oct - Nov'))

    def test_first_day_of_month_accepts_its_actual_boundary_week(self):
        pattern=planner_month_pattern(dt.datetime(2026,10,1,tzinfo=IST))
        self.assertIsNotNone(pattern.fullmatch('Sep - Oct'))
        self.assertIsNone(pattern.fullmatch('Oct - Nov'))
