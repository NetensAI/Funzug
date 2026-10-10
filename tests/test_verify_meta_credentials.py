import json
import unittest
from unittest.mock import patch

from scripts.verify_meta_credentials import verify_object


class VerifyMetaCredentialsTests(unittest.TestCase):
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
        self.assertNotIn("secret-token", request.full_url)
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


if __name__ == "__main__":
    unittest.main()
