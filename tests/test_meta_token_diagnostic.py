import unittest

from scripts.meta_token_diagnostic import INSTAGRAM_SCOPES, PAGE_SCOPES, summarize


class DebugMetaTokensTests(unittest.TestCase):
    def test_valid_page_token_reports_required_scopes_without_identity_fields(self):
        payload = {
            "data": {
                "app_id": "2180210799547573",
                "is_valid": True,
                "expires_at": 2000000000,
                "data_access_expires_at": 2000000000,
                "scopes": sorted(PAGE_SCOPES),
                "user_id": "private-identifier",
            }
        }
        summary, passed = summarize(payload, "2180210799547573", PAGE_SCOPES)
        self.assertTrue(passed)
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["missing_scopes"], [])
        self.assertNotIn("user_id", summary)

    def test_missing_scope_fails(self):
        payload = {"data": {"app_id": "2180210799547573", "is_valid": True, "scopes": ["pages_show_list"]}}
        summary, passed = summarize(payload, "2180210799547573", PAGE_SCOPES)
        self.assertFalse(passed)
        self.assertIn("pages_manage_posts", summary["missing_scopes"])

    def test_wrong_app_or_invalid_token_fails(self):
        payload = {"data": {"app_id": "other-app", "is_valid": False, "scopes": sorted(INSTAGRAM_SCOPES)}}
        summary, passed = summarize(payload, "2180210799547573", INSTAGRAM_SCOPES)
        self.assertFalse(passed)
        self.assertFalse(summary["valid"])
        self.assertFalse(summary["app_match"])

    def test_malformed_payload_fails_closed(self):
        summary, passed = summarize({"error": {"message": "must not be returned"}}, "2180210799547573", PAGE_SCOPES)
        self.assertFalse(passed)
        self.assertEqual(summary["scopes"], [])
        self.assertNotIn("must not be returned", repr(summary))


if __name__ == "__main__":
    unittest.main()
