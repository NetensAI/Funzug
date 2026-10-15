import json
import unittest
from pathlib import Path
from unittest.mock import patch

import instagram_credentials as credentials
from scripts import renew_instagram_credential as renewal


class InstagramCredentialTests(unittest.TestCase):
    def setUp(self):
        self.now = 1900000000
        self.bundle = credentials.make_bundle("test-secret", "123", self.now - 7 * 86400, self.now + 40 * 86400)

    def test_expired_or_changed_token_fails_closed(self):
        for field, value in (("expires_at", self.now), ("access_token", "changed-secret"), ("app_id", "wrong-app")):
            altered = dict(self.bundle, **{field: value})
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                credentials.decode_bundle(json.dumps(altered), self.now)

    def test_refresh_rejects_wrong_account_before_save(self):
        with patch.object(credentials, "request_json", return_value={"access_token": "new-secret", "expires_in": 60 * 86400}), patch.object(credentials, "verify_account", side_effect=RuntimeError("wrong account")):
            with self.assertRaises(RuntimeError):
                credentials.refresh_bundle(self.bundle, self.now)

    def test_refresh_produces_one_consistent_bundle(self):
        with patch.object(credentials, "request_json", return_value={"access_token": "new-secret", "expires_in": 60 * 86400}), patch.object(credentials, "verify_account", return_value="123") as verify:
            refreshed = credentials.refresh_bundle(self.bundle, self.now)
        self.assertEqual(credentials.decode_bundle(json.dumps(refreshed), self.now)["access_token"], "new-secret")
        self.assertEqual(refreshed["expires_at"], self.now + 60 * 86400 - 300)
        verify.assert_called_once_with("new-secret", "123")

    def test_too_young_token_is_not_refreshed(self):
        recent = credentials.make_bundle("secret", "123", self.now - 3600, self.now + 50 * 86400)
        with patch.object(credentials, "request_json") as request, self.assertRaises(RuntimeError):
            credentials.refresh_bundle(recent, self.now)
        request.assert_not_called()

    def test_permission_failure_blocks_credential(self):
        responses = [{"id": "123", "username": "funzugdotcom"}, {"data": []}]
        with patch.object(credentials, "request_json", side_effect=responses), self.assertRaises(RuntimeError):
            credentials.verify_account("secret", "123")

    def test_redirects_are_refused(self):
        self.assertIsNone(credentials.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))

    def test_writer_failure_does_not_refresh_or_reveal_secret(self):
        with patch.object(renewal, "installation_token", side_effect=RuntimeError("sensitive-secret")), patch.object(renewal, "refresh_bundle") as refresh, patch("builtins.print") as output:
            self.assertEqual(renewal.main(), 1)
        refresh.assert_not_called()
        self.assertNotIn("sensitive-secret", str(output.call_args_list))

    def test_activation_requires_full_credential_check(self):
        with patch("scripts.meta_token_diagnostic.main", return_value=1), patch("urllib.request.build_opener") as request:
            with self.assertRaises(RuntimeError):
                renewal.activate_instagram_login(self.bundle, "fake-auth")
        request.assert_not_called()

    def test_bootstrap_cannot_activate_publisher(self):
        with patch.dict("os.environ", {"BOOTSTRAP_INSTAGRAM_LOGIN": "true", "ACTIVATE_AFTER_REFRESH": "true"}), patch.object(renewal, "installation_token", return_value="fake-auth"), patch.object(renewal, "save_bundle") as save, patch.object(renewal, "activate_instagram_login") as activate, patch("builtins.print"):
            self.assertEqual(renewal.main(), 1)
        save.assert_not_called()
        activate.assert_not_called()

    def test_instagram_renewal_uses_one_recurring_scheduler(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/renew-instagram-credential.yml").read_text()
        self.assertIn("on:\n  workflow_dispatch:", workflow)
        self.assertNotIn("\n  schedule:\n", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main' && (inputs.bootstrap || inputs.renew_now)", workflow)
        self.assertIn("environment: funzug-publish", workflow)


if __name__ == "__main__":
    unittest.main()
