import json
import io
import unittest
import urllib.parse
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.verify_meta_credentials import normalize_graph_version, verify_object


class VerifyMetaCredentialsTests(unittest.TestCase):
    def test_empty_graph_version_defaults_safely(self):
        self.assertEqual(normalize_graph_version(None), "26.0")
        self.assertEqual(normalize_graph_version(""), "26.0")
        self.assertEqual(normalize_graph_version("v26.0"), "26.0")

    def test_validates_expected_object_id(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({"id": "12345"}).encode()

        with patch("scripts.verify_meta_credentials.urllib.request.urlopen", return_value=Response()) as open_url:
            with patch("builtins.print"):
                self.assertTrue(verify_object("26.0", "12345", "secret-token", "Page"))

        request = open_url.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        self.assertNotIn("access_token", query)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")

    def test_rejects_mismatched_object_id(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"id":"other"}'

        with patch("scripts.verify_meta_credentials.urllib.request.urlopen", return_value=Response()):
            with patch("builtins.print"):
                self.assertFalse(verify_object("26.0", "expected", "secret-token", "Page"))

    def test_http_error_reports_only_safe_codes(self):
        response = HTTPError(
            "https://graph.facebook.com/",
            400,
            "Bad Request",
            hdrs=None,
            fp=io.BytesIO(
                b'{"error":{"type":"OAuthException","code":190,'
                b'"error_subcode":123,"message":"An active access token is required"}}'
            ),
        )
        with patch("scripts.verify_meta_credentials.urllib.request.urlopen", side_effect=response):
            with patch("builtins.print") as output:
                self.assertFalse(verify_object("26.0", "12345", "secret-token", "Page"))

        message = output.call_args.args[0]
        self.assertIn("OAuthException", message)
        self.assertIn("code 190", message)
        self.assertIn("token missing or inactive", message)
        self.assertNotIn("secret-token", message)
        self.assertIn("Meta message: An active access token is required", message)


if __name__ == "__main__":
    unittest.main()
