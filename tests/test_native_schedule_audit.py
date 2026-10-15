import copy
import datetime as dt
import unittest
from unittest.mock import Mock

from scheduler.audit_schedules import audit_packet
from scheduler.native_worker import IST, NativeFailure
from tests.test_native_worker import package, checkpoint, receipts


class NativeScheduleAuditTests(unittest.TestCase):
    def fixture(self):
        packet = package()
        packet['nativeHandoff'] = checkpoint(packet, 'submitting')
        packet['nativeHandoff'].update(state='scheduled', receipts=receipts(packet))
        browser = Mock()
        browser.inspect.return_value = receipts(packet)
        return packet, browser

    def test_existing_schedule_audit_reads_both_receipts_without_delivery(self):
        packet, browser = self.fixture()
        result = audit_packet(packet, browser, lambda: dt.datetime.now(IST))
        self.assertEqual(set(result), {'facebook', 'instagram'})
        browser.prepare.assert_not_called()
        browser.prepared.assert_not_called()
        browser.submit.assert_not_called()

    def test_missing_or_conflicting_receipt_does_not_report_success(self):
        packet, browser = self.fixture()
        for observed in [{}, {'facebook': receipts(packet)['facebook']},
                         {**receipts(packet), 'instagram': {**receipts(packet)['instagram'], 'schedule_id':'999'}}]:
            browser.inspect.return_value = copy.deepcopy(observed)
            with self.assertRaisesRegex(NativeFailure, 'stored_schedule_not_visible_in_planner'):
                audit_packet(packet, browser, lambda: dt.datetime.now(IST))
            browser.submit.assert_not_called()

    def test_unsubmitted_package_is_not_opened_in_planner(self):
        packet, browser = self.fixture()
        packet['nativeHandoff']['state'] = 'reserved'
        with self.assertRaisesRegex(NativeFailure, 'audit_requires_existing_schedule'):
            audit_packet(packet, browser, lambda: dt.datetime.now(IST))
        browser.inspect.assert_not_called()
