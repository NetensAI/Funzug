from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from scheduler.meta_browser import MetaBrowser
from scheduler.native_runner import tick, shutdown_requested
from scheduler.native_worker import IST
import datetime as dt


class NativeBrowserCleanupTests(unittest.TestCase):
    def test_incomplete_browser_creation_closes_its_first_owned_tab(self):
        context, page = Mock(), Mock()
        context.new_page.side_effect = [page, RuntimeError('fixture failure')]
        with self.assertRaises(RuntimeError):
            MetaBrowser(context, Path('.'))
        page.close.assert_called_once()

    def test_second_owned_tab_closes_even_if_first_close_fails(self):
        context, first, second = Mock(), Mock(), Mock()
        context.new_page.side_effect = [first, second]
        browser = MetaBrowser(context, Path('.'))
        first.close.side_effect = RuntimeError('fixture failure')
        with self.assertRaises(RuntimeError):
            browser.close()
        second.close.assert_called_once()

    def test_shutdown_interrupt_closes_worker_tabs_without_resubmission(self):
        row={'externalId':'approved','status':'approved','publicationAuthorized':True,
             'scheduleTimezone':'Asia/Kolkata','proposedSchedule':(dt.datetime.now(IST)+dt.timedelta(days=1)).isoformat()}
        driver=Mock()
        with patch('scheduler.native_runner.read_api',side_effect=[{'drafts':[row]},{}]),patch('scheduler.native_runner.auth',return_value='fixture'),patch('scheduler.native_runner.write_state'),patch('scheduler.native_runner.CheckpointDispatcher'),patch('scheduler.native_runner.advance',side_effect=lambda *args:shutdown_requested(None,None)),patch('scheduler.meta_browser.MetaBrowser',return_value=driver):
            with self.assertRaises(KeyboardInterrupt):
                tick({},Path('nonexistent-native-cleanup-state.json'),None,True)
        driver.close.assert_called_once()
        driver.submit.assert_not_called()
