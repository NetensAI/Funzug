import datetime as dt
import unittest
from scheduler.publication_evidence import publication_time
from scheduler.native_worker import IST,NativeFailure


class PublicationEvidenceTests(unittest.TestCase):
    def test_visible_published_time_is_parsed_in_ist(self):
        now=dt.datetime(2026,10,13,17,0,tzinfo=IST)
        self.assertEqual(publication_time('Post · Published on: Tue Oct 13, 10:16am','2026-10-13T10:16:00+05:30',now),'2026-10-13T10:16:00+05:30')

    def test_schedule_relative_time_and_wrong_weekday_are_not_evidence(self):
        now=dt.datetime(2026,10,13,17,0,tzinfo=IST)
        for label in ['Scheduled for: Tue Oct 13, 10:16am','7 hours ago','Post · Published on: Mon Oct 13, 10:16am','Post · Published on: Tue Oct 13, 10:99am']:
            with self.assertRaises(NativeFailure):
                publication_time(label,'2026-10-13T10:16:00+05:30',now)

    def test_wrong_time_and_future_publication_fail(self):
        now=dt.datetime(2026,10,13,17,0,tzinfo=IST)
        for label in ['Post · Published on: Tue Oct 13, 11:16am','Post · Published on: Tue Oct 13, 6:26pm']:
            with self.assertRaises(NativeFailure):
                publication_time(label,'2026-10-13T10:16:00+05:30',now)
