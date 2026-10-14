from pathlib import Path
import unittest
from unittest.mock import MagicMock

from scheduler.meta_browser import MetaBrowser, REEL_DATE
from scheduler.native_worker import NativeFailure


class ReelScheduleFieldsTests(unittest.TestCase):
    def setUp(self):
        self.browser=MetaBrowser(MagicMock(),Path('.'))
        self.browser.visible=MagicMock()
        self.browser.set_schedule_fields=MagicMock()
        self.option=self.browser.page.get_by_role.return_value.and_.return_value
        self.option.count.return_value=1
        self.packet={'scheduleTimezone':'Asia/Kolkata'}

    def test_selects_option_not_final_submit_and_uses_reel_date_label(self):
        self.option.get_attribute.side_effect=['false','true']
        self.browser.set_reel_schedule(self.packet)
        self.option.click.assert_called_once()
        self.browser.page.get_by_role.return_value.click.assert_not_called()
        self.browser.set_schedule_fields.assert_called_once_with(self.packet,REEL_DATE)

    def test_already_selected_option_is_not_clicked_again(self):
        self.option.get_attribute.return_value='true'
        self.browser.set_reel_schedule(self.packet)
        self.option.click.assert_not_called()

    def test_ambiguous_or_unconfirmed_option_cannot_enter_times(self):
        for count,pressed in [(2,'false'),(0,'false'),(1,'false')]:
            self.option.count.return_value=count
            self.option.get_attribute.return_value=pressed
            with self.assertRaises(NativeFailure):
                self.browser.set_reel_schedule(self.packet)
        self.browser.set_schedule_fields.assert_not_called()

    def test_exact_ist_fields_are_read_back_for_every_platform(self):
        self.browser.timezone=MagicMock()
        controls={}
        for name in (REEL_DATE,'hours','minutes','meridiem'):
            control=MagicMock();control.count.return_value=2
            control.nth.return_value.input_value.return_value='Oct 14, 2099'
            control.nth.return_value.get_attribute.return_value={'hours':'7','minutes':'30','meridiem':'1'}.get(name)
            controls[name]=control
        self.browser.page.get_by_role.side_effect=lambda role,name,exact:controls[name]
        packet={'scheduleTimezone':'Asia/Kolkata','platforms':['facebook','instagram'],'proposedSchedule':'2099-10-14T19:30:00+05:30'}
        self.browser.verify_schedule_fields(packet,REEL_DATE)
        controls['minutes'].count.return_value=3
        with self.assertRaisesRegex(NativeFailure,'platform_time_controls_changed'):
            self.browser.verify_schedule_fields(packet,REEL_DATE)
        controls['minutes'].count.return_value=2
        controls['minutes'].nth.return_value.get_attribute.return_value='31'
        with self.assertRaisesRegex(NativeFailure,'time_entry_unconfirmed'):
            self.browser.verify_schedule_fields(packet,REEL_DATE)
