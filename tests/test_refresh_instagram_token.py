import base64
import io
import importlib.util
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

from scripts import refresh_instagram_token as refresh


class RefreshInstagramTokenTests(unittest.TestCase):
    def test_meta_refresh_uses_instagram_login_endpoint_and_returns_metadata(self):
        response = {"access_token": "refreshed-token-value", "expires_in": 5_184_000}
        with patch.object(refresh, "request_json", return_value=(200, response)) as request_json:
            token, lifetime = refresh.meta_refresh("original-token-value")
        request = request_json.call_args.args[0]
        params = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(urlparse(request.full_url).hostname, "graph.instagram.com")
        self.assertEqual(params["grant_type"], ["ig_refresh_token"])
        self.assertEqual(params["access_token"], ["original-token-value"])
        self.assertEqual(token, "refreshed-token-value")
        self.assertEqual(lifetime, 5_184_000)

    def test_meta_refresh_rejects_short_or_malformed_lifetime(self):
        with patch.object(refresh, "request_json", return_value=(200, {"access_token": "x", "expires_in": 10})):
            with self.assertRaisesRegex(RuntimeError, "invalid token refresh response"):
                refresh.meta_refresh("input-token")

    def test_request_json_accepts_empty_success_body(self):
        response = MagicMock()
        response.status = 204
        response.read.return_value = b""
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(refresh, "build_opener", return_value=opener):
            status, payload = refresh.request_json(Request("https://api.github.com/example"))
        self.assertEqual(status, 204)
        self.assertEqual(payload, {})

    def test_environment_secret_update_encrypts_and_targets_only_instagram_secret(self):
        responses = [
            {"key": "public-key", "key_id": "key-id"},
            {},
        ]
        with patch.object(refresh, "github_request", side_effect=responses) as github_request:
            with patch.object(refresh, "encrypt_secret_value", return_value="ciphertext") as encrypt:
                refresh.replace_environment_secret("new-instagram-token", "installation-token")
        self.assertEqual(encrypt.call_args.args, ("public-key", "new-instagram-token"))
        calls = github_request.call_args_list
        self.assertEqual(calls[0].args[:2], (
            "GET",
            "/repos/NetensAI/Funzug/environments/funzug-publish/secrets/public-key",
        ))
        self.assertEqual(calls[1].args[:2], (
            "PUT",
            "/repos/NetensAI/Funzug/environments/funzug-publish/secrets/FUNZUG_INSTAGRAM_ACCESS_TOKEN",
        ))
        self.assertEqual(calls[1].args[3], {"encrypted_value": "ciphertext", "key_id": "key-id"})

    @unittest.skipUnless(importlib.util.find_spec("nacl"), "PyNaCl is installed in CI")
    def test_secret_encryption_uses_github_sealed_box_format(self):
        from nacl.public import PrivateKey, SealedBox

        private_key = PrivateKey.generate()
        encrypted = refresh.encrypt_secret_value(
            base64.b64encode(bytes(private_key.public_key)).decode(),
            "private-token-value",
        )
        plaintext = SealedBox(private_key).decrypt(base64.b64decode(encrypted))
        self.assertEqual(plaintext, b"private-token-value")

    def test_missing_inputs_fail_without_network_calls(self):
        with patch.dict("os.environ", {"FUNZUG_INSTAGRAM_API_MODE": "instagram_login"}, clear=True):
            with patch.object(refresh, "meta_refresh") as meta_refresh:
                with patch("builtins.print") as print_output:
                    self.assertEqual(refresh.main(), 1)
        meta_refresh.assert_not_called()
        self.assertNotIn("test-secret-value", str(print_output.call_args))

    def test_refresh_does_not_persist_until_token_and_account_are_verified(self):
        env = {
            "FUNZUG_INSTAGRAM_API_MODE": "instagram_login",
            "FUNZUG_INSTAGRAM_ACCESS_TOKEN": "old-token",
            "FUNZUG_GH_APP_ID": "app-id",
            "FUNZUG_GH_APP_PRIVATE_KEY": "private-key",
            "FUNZUG_META_APP_SECRET": "app-secret",
            "FUNZUG_INSTAGRAM_USER_ID": "ig-user-id",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch.object(refresh, "meta_refresh", return_value=("new-token", 5_184_000)):
                with patch("scripts.meta_token_diagnostic.debug_token", return_value={"data": {}}):
                    with patch("scripts.meta_token_diagnostic.summarize", return_value=({}, False)):
                        with patch("scripts.verify_meta_credentials.verify_object") as verify:
                            with patch.object(refresh, "github_installation_token") as github_token:
                                with patch.object(refresh, "replace_environment_secret") as replace_secret:
                                    with patch("builtins.print"):
                                        self.assertEqual(refresh.main(), 1)
        verify.assert_not_called()
        github_token.assert_not_called()
        replace_secret.assert_not_called()

    def test_refresh_persists_only_after_scope_and_account_checks_pass(self):
        env = {
            "FUNZUG_INSTAGRAM_API_MODE": "instagram_login",
            "FUNZUG_INSTAGRAM_ACCESS_TOKEN": "old-token",
            "FUNZUG_GH_APP_ID": "app-id",
            "FUNZUG_GH_APP_PRIVATE_KEY": "private-key",
            "FUNZUG_META_APP_SECRET": "app-secret",
            "FUNZUG_INSTAGRAM_USER_ID": "ig-user-id",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch.object(refresh, "meta_refresh", return_value=("new-token", 5_184_000)):
                with patch("scripts.meta_token_diagnostic.debug_token", return_value={"data": {}}):
                    with patch("scripts.meta_token_diagnostic.summarize", return_value=({}, True)):
                        with patch("scripts.verify_meta_credentials.verify_object", return_value=True):
                            with patch.object(refresh, "github_installation_token", return_value="gh-install-token"):
                                with patch.object(refresh, "replace_environment_secret") as replace_secret:
                                    with patch("builtins.print"):
                                        self.assertEqual(refresh.main(), 0)
        replace_secret.assert_called_once_with("new-token", "gh-install-token")

    def test_facebook_login_mode_skips_refresh_without_network_calls(self):
        with patch.dict("os.environ", {"FUNZUG_INSTAGRAM_API_MODE": "facebook_login"}, clear=True):
            with patch.object(refresh, "meta_refresh") as meta_refresh:
                with patch("builtins.print"):
                    self.assertEqual(refresh.main(), 0)
        meta_refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
