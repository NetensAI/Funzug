import unittest
import os
from unittest.mock import patch

from scripts.meta_token_diagnostic import (
    INSTAGRAM_LOGIN_SCOPES,
    INSTAGRAM_SCOPES,
    PAGE_SCOPES,
    main,
    summarize,
)


class DebugMetaTokensTests(unittest.TestCase):
    def test_valid_page_token_reports_required_scopes_without_identity_fields(self):
        payload = {
            "data": {
                "app_id": "2180210799547573",
                "is_valid": True,
                "expires_at": 0,
                "data_access_expires_at": 0,
                "scopes": sorted(PAGE_SCOPES),
                "user_id": "private-identifier",
            }
        }
        summary, passed = summarize(payload, "2180210799547573", PAGE_SCOPES, now=1900000000)
        self.assertTrue(passed)
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["missing_scopes"], [])
        self.assertTrue(summary["explicitly_non_expiring"])
        self.assertNotIn("user_id", summary)

    def test_instagram_login_scope_set_is_distinct_from_facebook_login(self):
        self.assertEqual(
            INSTAGRAM_LOGIN_SCOPES,
            {"instagram_business_basic", "instagram_business_content_publish"},
        )
        self.assertNotEqual(INSTAGRAM_LOGIN_SCOPES, INSTAGRAM_SCOPES)

    def test_diagnostic_uses_instagram_login_scopes_when_selected(self):
        valid_page = {
            "data": {
                "app_id": "2180210799547573",
                "is_valid": True,
                "expires_at": 0,
                "data_access_expires_at": 0,
                "scopes": sorted(PAGE_SCOPES),
            }
        }
        valid_instagram = {
            "data": {
                "app_id": "2180210799547573",
                "is_valid": True,
                "expires_at": 0,
                "data_access_expires_at": 0,
                "scopes": sorted(INSTAGRAM_LOGIN_SCOPES),
            }
        }
        with patch.dict(os.environ, {
            "FUNZUG_META_APP_SECRET": "test-app-secret",
            "FUNZUG_FACEBOOK_PAGE_TOKEN": "page-token",
            "FUNZUG_INSTAGRAM_ACCESS_TOKEN": "instagram-token",
            "FUNZUG_INSTAGRAM_API_MODE": "instagram_login",
        }):
            with patch("scripts.meta_token_diagnostic.debug_token", side_effect=[valid_page, valid_instagram]) as debug:
                with patch("builtins.print"):
                    self.assertEqual(main(), 0)
        self.assertEqual(debug.call_args_list[1].args[2], "instagram-token")

    def test_finite_lifetime_token_is_not_ready_even_if_far_in_future(self):
        payload = {
            "data": {
                "app_id": "2180210799547573",
                "is_valid": True,
                "expires_at": 1900000000 + 86400 * 365,
                "data_access_expires_at": 1900000000 + 86400 * 365,
                "scopes": sorted(PAGE_SCOPES),
            }
        }
        summary, passed = summarize(payload, "2180210799547573", PAGE_SCOPES, now=1900000000)
        self.assertFalse(passed)
        self.assertFalse(summary["explicitly_non_expiring"])
        self.assertFalse(summary["lifetime_ready"])

    def test_instagram_login_accepts_finite_lifetime_with_refresh_margin(self):
        payload = {
            "data": {
                "app_id": "2180210799547573",
                "is_valid": True,
                "expires_at": 1900000000 + 86400 * 30,
                "data_access_expires_at": 1900000000 + 86400 * 30,
                "scopes": sorted(INSTAGRAM_LOGIN_SCOPES),
            }
        }
        summary, passed = summarize(
            payload, "2180210799547573", INSTAGRAM_LOGIN_SCOPES,
            now=1900000000, allow_expiring=True,
        )
        self.assertTrue(passed)
        self.assertFalse(summary["explicitly_non_expiring"])
        self.assertTrue(summary["lifetime_ready"])

    def test_instagram_login_fails_when_refresh_margin_is_under_seven_days(self):
        payload = {
            "data": {
                "app_id": "2180210799547573",
                "is_valid": True,
                "expires_at": 1900000000 + 86400 * 6,
                "data_access_expires_at": 1900000000 + 86400 * 6,
                "scopes": sorted(INSTAGRAM_LOGIN_SCOPES),
            }
        }
        summary, passed = summarize(
            payload, "2180210799547573", INSTAGRAM_LOGIN_SCOPES,
            now=1900000000, allow_expiring=True,
        )
        self.assertFalse(passed)
        self.assertFalse(summary["lifetime_ready"])

    def test_non_expiring_tokens_can_pass_with_explicit_zero_expiry(self):
        payload = {
            "data": {
                "app_id": "2180210799547573",
                "is_valid": True,
                "expires_at": 0,
                "data_access_expires_at": 0,
                "scopes": sorted(PAGE_SCOPES),
            }
        }
        summary, passed = summarize(payload, "2180210799547573", PAGE_SCOPES, now=1900000000)
        self.assertTrue(passed)
        self.assertTrue(summary["explicitly_non_expiring"])

    def test_missing_expiry_metadata_fails_closed(self):
        payload = {
            "data": {
                "app_id": "2180210799547573",
                "is_valid": True,
                "scopes": sorted(PAGE_SCOPES),
            }
        }
        summary, passed = summarize(payload, "2180210799547573", PAGE_SCOPES)
        self.assertFalse(passed)
        self.assertFalse(summary["explicitly_non_expiring"])

    def test_missing_scope_fails(self):
        payload = {"data": {"app_id": "2180210799547573", "is_valid": True, "scopes": ["pages_show_list"]}}
        summary, passed = summarize(payload, "2180210799547573", PAGE_SCOPES, now=1900000000)
        self.assertFalse(passed)
        self.assertIn("pages_manage_posts", summary["missing_scopes"])

    def test_wrong_app_or_invalid_token_fails(self):
        payload = {"data": {"app_id": "other-app", "is_valid": False, "scopes": sorted(INSTAGRAM_SCOPES)}}
        summary, passed = summarize(payload, "2180210799547573", INSTAGRAM_SCOPES, now=1900000000)
        self.assertFalse(passed)
        self.assertFalse(summary["valid"])
        self.assertFalse(summary["app_match"])

    def test_malformed_payload_fails_closed(self):
        summary, passed = summarize({"error": {"message": "must not be returned"}}, "2180210799547573", PAGE_SCOPES, now=1900000000)
        self.assertFalse(passed)
        self.assertEqual(summary["scopes"], [])
        self.assertNotIn("must not be returned", repr(summary))


if __name__ == "__main__":
    unittest.main()
