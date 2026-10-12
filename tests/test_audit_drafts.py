import datetime as dt
import unittest
from scripts.audit_drafts import audit, IST


class DraftAuditTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 12, 12, tzinfo=IST)
        self.item = {'id': 'draft', 'topic_key': 'new',
                     'scheduled_at': '2026-11-08T03:30:00+05:30', 'caption': 'A meteor shower.'}

    def test_future_evergreen_has_no_heuristic_warning(self):
        self.assertEqual(audit({'items': [self.item]}, {}, self.now), [])

    def test_relative_wording_is_flagged_without_mutation(self):
        self.item['caption'] = 'Will you watch this month?'
        before = dict(self.item)
        self.assertIn('relative-date', audit({'items': [self.item]}, {}, self.now)[0]['warnings'][0])
        self.assertEqual(before, self.item)

    def test_history_and_inbox_duplicates(self):
        result = audit({'items': [self.item, self.item]}, {'topic_keys': ['new']}, self.now)
        self.assertEqual(len(result[0]['warnings']), 1)
        self.assertEqual(len(result[1]['warnings']), 2)

    def test_past_and_naive_time_are_flagged(self):
        for time in ['2026-10-11T10:00:00+05:30', '2026-11-08T10:00:00', 'bad']:
            with self.subTest(time=time):
                self.item['scheduled_at'] = time
                self.assertTrue(audit({'items': [self.item]}, {}, self.now))
