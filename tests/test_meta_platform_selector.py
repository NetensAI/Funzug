import unittest
from unittest.mock import Mock, patch

from scheduler.meta_browser import MetaBrowser
from scheduler.native_worker import NativeFailure


class AccountRow:
    def __init__(self, selected):
        self.selected = selected
        self.click = Mock(side_effect=self.toggle)

    def toggle(self):
        self.selected = not self.selected

    def count(self):
        return 1

    def get_attribute(self, name):
        if name in {'aria-selected', 'aria-checked'}:
            return str(self.selected).lower()
        return None


class AccountList:
    def __init__(self, rows):
        self.rows = rows

    def count(self):
        return 1

    def get_by_text(self, name, exact):
        assert exact is True
        return self.rows.get(name, MissingRow())


class MissingRow:
    def count(self):
        return 0


class AccountSelectorTests(unittest.TestCase):
    def test_visible_meta_block_stops_before_any_account_action(self):
        browser = MetaBrowser.__new__(MetaBrowser)
        page = Mock()
        page.get_by_text.return_value.count.return_value = 1
        with self.assertRaisesRegex(NativeFailure,'meta_temporarily_blocked'):
            browser.check_access(page)
        page.get_by_role.assert_not_called()

    def test_caption_mentioning_funzug_is_not_an_account_selector(self):
        browser = MetaBrowser.__new__(MetaBrowser)
        browser.page = Mock()
        account = Mock()
        account.count.return_value = 1
        account.inner_text.return_value = 'Instagram Facebook Funzug and funzugdotcom'
        broad = Mock()
        broad.filter.return_value.count.return_value = 2

        def by_role(role, **options):
            self.assertEqual(role, 'combobox')
            name = options.get('name')
            if name is None:
                return broad
            self.assertIsNotNone(name.search('Post to Funzug and funzugdotcom'))
            self.assertIsNone(name.search('Write into the dialogue box to include text with your post.'))
            return account

        browser.page.get_by_role.side_effect = by_role
        self.assertEqual(browser.selected_platforms(), ['facebook', 'instagram'])
        broad.filter.assert_not_called()

    def fixture(self, facebook=True, instagram=True):
        browser = MetaBrowser.__new__(MetaBrowser)
        browser.page = Mock()
        selector = Mock()
        selector.count.return_value = 1
        def selected_label():
            facebook = rows['Funzug'].selected
            instagram = rows['funzugdotcom'].selected
            if facebook and instagram:
                return 'Instagram Facebook Funzug and funzugdotcom'
            if facebook:
                return 'Funzug'
            if instagram:
                return 'funzugdotcom'
            return ''

        selector.inner_text.side_effect = selected_label
        selector.filter.return_value = selector
        browser.page.get_by_role.return_value = selector
        rows = {'Funzug': AccountRow(facebook), 'funzugdotcom': AccountRow(instagram)}
        account_list = AccountList(rows)

        def get_by_role(role, **kwargs):
            if role == 'combobox':
                return selector
            if role == 'option':
                return MissingRow()
            if role == 'list' and kwargs == {'name': 'Post to', 'exact': True}:
                return account_list
            raise AssertionError((role, kwargs))

        browser.page.get_by_role.side_effect = get_by_role
        browser.page.keyboard = Mock()
        return browser, rows

    def test_uses_current_meta_list_rows_to_select_one_account(self):
        browser, rows = self.fixture()

        browser.select_platforms(['instagram'])

        self.assertTrue(rows['Funzug'].click.called)
        self.assertFalse(rows['funzugdotcom'].click.called)
        self.assertEqual(browser.selected_platforms(), ['instagram'])

    def test_unknown_or_ambiguous_selection_fails_closed(self):
        browser, rows = self.fixture()
        rows['Funzug'].get_attribute = lambda name: None

        with self.assertRaisesRegex(NativeFailure, 'account_selection_unconfirmed'):
            browser.select_platforms(['instagram'])

        rows['Funzug'].click.assert_not_called()


class ReelProcessingWaitTests(unittest.TestCase):
    def setUp(self):
        self.browser = MetaBrowser.__new__(MetaBrowser)
        self.browser.page = Mock()

    def test_waits_for_meta_reel_processing(self):
        button = Mock()
        button.is_enabled.side_effect = [False, False, True]
        with patch('scheduler.meta_browser.time.monotonic', side_effect=[1, 1.1, 1.2]):
            self.browser.wait_until_enabled(button, timeout_ms=1000)
        self.assertEqual(self.browser.page.wait_for_timeout.call_count, 2)

    def test_times_out_when_reel_never_becomes_ready(self):
        button = Mock()
        button.is_enabled.return_value = False
        with patch('scheduler.meta_browser.time.monotonic', side_effect=[1, 2]):
            with self.assertRaisesRegex(NativeFailure, 'reel_processing_unconfirmed'):
                self.browser.wait_until_enabled(button, timeout_ms=500)
        self.browser.page.wait_for_timeout.assert_not_called()


if __name__ == '__main__':
    unittest.main()
