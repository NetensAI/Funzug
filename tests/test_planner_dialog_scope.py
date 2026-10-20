import unittest
import datetime as dt
from unittest.mock import Mock
from scheduler.meta_browser import MetaBrowser, calendar_label
from scheduler.native_worker import IST, NativeFailure


class PlannerDialogScopeTests(unittest.TestCase):
    def test_preclick_submission_checkpoint_does_not_wait_for_absent_post(self):
        driver = MetaBrowser.__new__(MetaBrowser)
        driver.planner = Mock()
        driver.visible = Mock()
        slot = dt.datetime.now(IST) + dt.timedelta(days=1)
        header, dates, cards = Mock(), Mock(), Mock()
        header.count.return_value = 1
        header.evaluate.return_value = {'left':0,'right':100}
        driver.planner.get_by_role.return_value.count.return_value = 1
        driver.planner.get_by_text.side_effect = lambda text, **kw: header if text == calendar_label(slot) else dates
        driver.planner.get_by_label.return_value = cards
        cards.all.return_value = []
        driver.planner_cards({'caption':'unsent reviewed caption',
            'proposedSchedule':slot.isoformat(),'nativeHandoff':{'state':'submitting'}},
            expect_existing=False)
        cards.first.wait_for.assert_not_called()

    def test_offscreen_card_hydrates_before_link_lookup(self):
        driver = MetaBrowser.__new__(MetaBrowser)
        driver.planner = Mock()
        driver.visible = Mock()
        slot = dt.datetime.now(IST) + dt.timedelta(days=1)
        header, dates, cards, card = Mock(), Mock(), Mock(), Mock()
        header.count.return_value = 1
        header.evaluate.return_value = {'left':0,'right':100}
        driver.planner.get_by_role.return_value.count.return_value = 1
        driver.planner.get_by_text.side_effect = lambda text, **kw: header if text == calendar_label(slot) else dates
        driver.planner.get_by_label.return_value = cards
        cards.all.return_value = [card]
        hydrated = []
        card.scroll_into_view_if_needed.side_effect = lambda **kw: hydrated.append(True)
        def loaded(**kw):
            self.assertTrue(hydrated, 'Facebook loading cannot complete offscreen')
        card.locator.return_value.wait_for.side_effect = loaded
        cards.get_by_role.return_value.count.side_effect = lambda: int(bool(hydrated))
        observed, _ = driver.planner_cards({'caption':'reviewed caption',
            'proposedSchedule':slot.isoformat(),'nativeHandoff':{'state':'scheduled'}})
        self.assertEqual(observed.get_by_role('link').count(),1)

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

    def test_horizontal_scroll_does_not_hide_second_platform_receipt(self):
        driver, dialog, close, packet = self.fixture()
        packet['platforms'] = ['facebook','instagram']
        cards = driver.planner_cards.return_value[0]
        first, second = Mock(), Mock()
        first.bounding_box.return_value = {'x':10,'width':10}
        second.bounding_box.return_value = {'x':210,'width':10}
        first_links, second_links = Mock(), Mock()
        first_links.all.return_value = [first]
        second_links.all.return_value = [second]
        cards.get_by_role.side_effect = [first_links, second_links]
        driver.planner.get_by_text.return_value.evaluate.return_value = {'left':200,'right':300}
        dialog.get_by_text.return_value.inner_text.side_effect = ['ID: 123','ID: 456']
        receipts = driver.inspect(packet)
        self.assertEqual({p:r['schedule_id'] for p,r in receipts.items()}, {'facebook':'123','instagram':'456'})
        self.assertEqual(close.click.call_count,2)

    def test_existing_facebook_card_must_finish_loading_before_absence_check(self):
        driver, dialog, close, packet = self.fixture()
        packet['nativeHandoff'] = {'state':'scheduled'}
        links = driver.planner_cards.return_value[0].get_by_role.return_value
        candidate = links.all.return_value[0]
        links.all.return_value = []
        def hydrate(**_):
            links.all.return_value = [candidate]
        links.first.wait_for.side_effect = hydrate
        self.assertEqual(driver.inspect(packet)['facebook']['schedule_id'], '123')

    def test_preclick_inspection_still_reports_existing_duplicate(self):
        driver, dialog, close, packet = self.fixture()
        packet['nativeHandoff'] = {'state':'submitting'}
        self.assertEqual(driver.inspect(packet, expect_existing=False)['facebook']['schedule_id'], '123')
        driver.planner_cards.assert_called_once_with(packet, expect_existing=False)
        driver.planner_cards.return_value[0].get_by_role.return_value.first.wait_for.assert_not_called()
