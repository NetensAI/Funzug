from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from scheduler.meta_browser import MetaBrowser
from scheduler.native_runner import tick, shutdown_requested
from scheduler.native_worker import IST
from scheduler.native_worker import NativeFailure
import datetime as dt


class NativeBrowserCleanupTests(unittest.TestCase):
    def test_missing_view_post_label_remains_pending_without_cooldown(self):
        browser = MetaBrowser(Mock(), Path('.'))
        browser.planner.url = 'https://business.facebook.com/latest/insights/object_insights/?content_id=123'
        locator=Mock()
        locator.wait_for.side_effect=TimeoutError()
        with patch.object(browser,'check_access') as access:
            with self.assertRaisesRegex(NativeFailure,'^publication_detail_pending$'):
                browser.publication_detail_wait(locator,15000)
        access.assert_called_once_with(browser.planner)
        locator.wait_for.assert_called_once_with(state='visible',timeout=15000)

    def test_missing_publication_heading_is_pending_not_global_timeout(self):
        browser = MetaBrowser(Mock(), Path('.'))
        browser.planner.url = 'https://business.facebook.com/latest/insights/object_insights/?content_id=123'
        browser.planner.get_by_role.return_value.wait_for.side_effect = TimeoutError()
        with patch.object(browser, 'check_access') as access:
            with self.assertRaisesRegex(NativeFailure, '^publication_detail_pending$'):
                browser.publication_heading('Exact approved caption')
        access.assert_called_once_with(browser.planner)
        browser.planner.get_by_role.assert_called_once_with('heading', name='Exact approved caption', exact=True)

    def test_publication_heading_preserves_actual_restriction(self):
        browser = MetaBrowser(Mock(), Path('.'))
        browser.planner.get_by_role.return_value.wait_for.side_effect = TimeoutError()
        with patch.object(browser, 'check_access', side_effect=NativeFailure('meta_temporarily_blocked')):
            with self.assertRaisesRegex(NativeFailure, '^meta_temporarily_blocked$'):
                browser.publication_heading('Exact approved caption')

    def test_publication_heading_login_is_not_publication_proof(self):
        browser = MetaBrowser(Mock(), Path('.'))
        browser.planner.url = 'https://business.facebook.com/login'
        browser.planner.get_by_role.return_value.wait_for.side_effect = TimeoutError()
        with patch.object(browser, 'check_access'):
            with self.assertRaisesRegex(NativeFailure, '^meta_login_required$'):
                browser.publication_heading('Exact approved caption')

    def test_publication_heading_does_not_hide_programming_errors(self):
        browser = MetaBrowser(Mock(), Path('.'))
        browser.planner.get_by_role.return_value.wait_for.side_effect = AttributeError('fixture')
        with self.assertRaises(AttributeError):
            browser.publication_heading('Exact approved caption')

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
