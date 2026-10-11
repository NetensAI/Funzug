import unittest
import importlib.util
import http.client
import threading
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import urllib.error
import urllib.request

from scripts import upload_media

SERVER_PATH = Path(__file__).parents[1] / "media-host" / "server.py"
SERVER_SPEC = importlib.util.spec_from_file_location("funzug_media_host", SERVER_PATH)
server = importlib.util.module_from_spec(SERVER_SPEC)
SERVER_SPEC.loader.exec_module(server)


class UploadMediaTests(unittest.TestCase):
    def image_file(self):
        handle = NamedTemporaryFile(suffix=".png", dir=Path(__file__).parent, delete=False)
        path = Path(handle.name)
        handle.close()
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
            + (1080).to_bytes(4, "big") + (1350).to_bytes(4, "big") + b"test payload"
        )
        return path

    def test_requires_https_public_origin(self):
        for origin in ("http://media.example.com", "https://user:pass@media.example.com", "https://media.example.com/?token=x"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                upload_media.public_origin(origin)

    def test_upload_uses_auth_header_and_returns_only_validated_public_url(self):
        path = self.image_file()

        class Response:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self, size):
                return b"/media/0123456789abcdef0123456789abcdef.png"

        class Opener:
            def open(self, request, timeout):
                return fake_urlopen(request, timeout)

        def fake_urlopen(request, timeout):
            self.assertEqual(request.full_url, "https://media.example.com/upload")
            self.assertEqual(request.get_header("Authorization"), "Bearer secret-value")
            self.assertEqual(request.get_header("Content-type"), "image/png")
            self.assertEqual(timeout, 30)
            return Response()

        with patch.object(upload_media.urllib.request, "build_opener", return_value=Opener()):
            result = upload_media.upload(path, "https://media.example.com", "secret-value")
        self.assertEqual(result, "https://media.example.com/media/0123456789abcdef0123456789abcdef.png")

    def test_refuses_invalid_host_return_path(self):
        path = self.image_file()

        class Response:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self, size):
                return b"https://evil.example/file.png"

        class Opener:
            def open(self, request, timeout):
                return Response()

        with patch.object(upload_media.urllib.request, "build_opener", return_value=Opener()):
            with self.assertRaisesRegex(RuntimeError, "invalid public path"):
                upload_media.upload(path, "https://media.example.com", "secret-value")

    def test_http_client_rejects_redirect_responses(self):
        redirect = upload_media.RejectRedirects()
        request = urllib.request.Request("https://media.example.com/upload", data=b"image", method="POST")
        self.assertIsNone(redirect.redirect_request(request, None, 302, "Found", {}, "https://attacker.example/"))

    def test_upload_refuses_noncompliant_dimensions_before_network(self):
        path = self.image_file()
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
            + (1200).to_bytes(4, "big") + (1500).to_bytes(4, "big") + b"test payload"
        )
        with self.assertRaisesRegex(ValueError, "1080x1350"):
            upload_media.upload(path, "https://media.example.com", "secret-value")

    def test_media_host_upload_then_public_read_round_trip(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as folder:
            prior_media_dir = server.MEDIA_DIR
            server.MEDIA_DIR = Path(folder)
            try:
                httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            except PermissionError:
                server.MEDIA_DIR = prior_media_dir
                self.skipTest("sandbox does not permit local socket binding")
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.object(server, "read_upload_token", return_value=b"local-test-upload-token"):
                    connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
                    data = (
                        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
                        + (1080).to_bytes(4, "big") + (1350).to_bytes(4, "big")
                        + b"example-png-payload"
                    )
                    connection.request("POST", "/upload", data, {
                        "Authorization": "Bearer local-test-upload-token",
                        "Content-Type": "image/png",
                    })
                    response = connection.getresponse()
                    self.assertEqual(response.status, 201)
                    media_path = response.read().decode("ascii")
                    connection.request("GET", media_path)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), "image/png")
                    self.assertEqual(response.read(), data)
                    connection.close()
            except PermissionError:
                self.skipTest("sandbox does not permit local socket connections")
            finally:
                httpd.shutdown()
                thread.join(timeout=2)
                httpd.server_close()
                server.MEDIA_DIR = prior_media_dir

    def test_server_requires_bearer_upload_secret(self):
        token = b"a-long-random-test-token"
        self.assertTrue(server.authorized("Bearer a-long-random-test-token", token))
        self.assertFalse(server.authorized("Bearer wrong", token))
        self.assertFalse(server.authorized(None, token))
        self.assertFalse(server.authorized("Basic a-long-random-test-token", token))

    def test_server_checks_image_signatures_against_content_type(self):
        self.assertEqual(server.image_extension(b"\x89PNG\r\n\x1a\nrest", "image/png"), ".png")
        self.assertEqual(server.image_extension(b"\xff\xd8\xffrest", "image/jpeg"), ".jpeg")
        self.assertIsNone(server.image_extension(b"not an image", "image/png"))
        self.assertIsNone(server.image_extension(b"\x89PNG\r\n\x1a\n", "text/html"))


if __name__ == "__main__":
    unittest.main()
