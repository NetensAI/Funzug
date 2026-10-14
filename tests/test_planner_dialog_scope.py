import unittest
from unittest.mock import Mock
from scheduler.meta_browser import MetaBrowser
from scheduler.native_worker import NativeFailure


class PlannerDialogScopeTests(unittest.TestCase):
    def fixture(self, dialog_count=1):
        driver = MetaBrowser.__new__(MetaBrowser)
        driver.planner = Mock(url='https://business.facebook.com/latest/content_calendar')
        dialog = Mock()
        dialog.count.return_value = dialog_count
        driver.planner.get_by_role.return_value = dialog
        identifier = dialog.get_by_text.return_value
        identifier.count.return_value = 1
        identifier.inner_text.return_value = 'ID: 123'
        close = dialog.get_by_role.return_value
        close.count.return_value = 1
        cards = Mock()
        candidate = Mock()
        candidate.bounding_box.return_value = {'x': 10, 'width': 10}
        cards.get_by_role.return_value.all.return_value = [candidate]
        driver.planner_cards = Mock(return_value=(cards, {'left': 0, 'right': 100}))
        packet = {'platforms': ['facebook'], 'proposedSchedule': '2026-10-17T16:30:00+05:30',
                  'format': 'image', 'contentHash': 'reviewed-hash'}
        return driver, dialog, close, packet

    def test_receipt_and_close_are_scoped_to_unique_detail_dialog(self):
        driver, dialog, close, packet = self.fixture()
        receipts = driver.inspect(packet)
        self.assertEqual(receipts['facebook']['schedule_id'], '123')
        driver.planner.get_by_role.assert_called_once_with('dialog', name='Post details', exact=True)
        dialog.get_by_role.assert_called_once_with('button', name='Close', exact=True)
        close.click.assert_called_once()
        driver.planner.get_by_text.assert_not_called()

    def test_duplicate_detail_dialogs_fail_without_closing_anything(self):
        driver, dialog, close, packet = self.fixture(2)
        with self.assertRaisesRegex(NativeFailure, 'planner_detail_not_unique'):
            driver.inspect(packet)
        close.click.assert_not_called()
        dialog.get_by_text.assert_not_called()
