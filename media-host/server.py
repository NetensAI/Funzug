"""Small authenticated image receiver with read-only public media URLs."""
from __future__ import annotations

import hmac
import os
from pathlib import Path
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "/data"))
TOKEN_FILE = Path(os.environ.get("UPLOAD_TOKEN_FILE", "/run/secrets/upload_token"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", "12582912"))
PORT = int(os.environ.get("PORT", "8080"))
CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def read_upload_token(path: Path = TOKEN_FILE) -> bytes:
    token = path.read_bytes().strip()
    if len(token) < 32:
        raise RuntimeError("upload token must contain at least 32 bytes")
    return token


def authorized(header: str | None, token: bytes) -> bool:
    if not isinstance(header, str) or not header.startswith("Bearer "):
        return False
    candidate = header[7:].encode("utf-8")
    return hmac.compare_digest(candidate, token)


def image_extension(data: bytes, content_type: str) -> str | None:
    extension = {value: key for key, value in CONTENT_TYPES.items()}.get(content_type.lower())
    if extension in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff"):
        return extension
    if extension == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return extension
    if extension == ".webp" and len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return extension
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = ""
    sys_version = ""

    def log_message(self, fmt: str, *args: object) -> None:
        # The standard log includes no headers or request body. Keep it minimal.
        print("media-host: " + (fmt % args), flush=True)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        match = re.fullmatch(r"/media/([0-9a-f]{32})\.(jpg|jpeg|png|webp)", self.path)
        if not match:
            self.send_error(404)
            return
        filename = match.group(1) + "." + match.group(2)
        path = MEDIA_DIR / filename
        try:
            size = path.stat().st_size
            handle = path.open("rb")
        except OSError:
            self.send_error(404)
            return
        with handle:
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPES[path.suffix])
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            while chunk := handle.read(64 * 1024):
                self.wfile.write(chunk)

    def do_POST(self) -> None:
        if self.path != "/upload":
            self.send_error(404)
            return
        try:
            token = read_upload_token()
        except (OSError, RuntimeError):
            self.send_error(503)
            return
        if not authorized(self.headers.get("Authorization"), token):
            self.send_error(401)
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            self.send_error(400)
            return
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            self.send_error(413 if length > MAX_UPLOAD_BYTES else 400)
            return
        data = self.rfile.read(length)
        if len(data) != length:
            self.send_error(400)
            return
        extension = image_extension(data, self.headers.get("Content-Type", ""))
        if extension is None:
            self.send_error(415)
            return
        filename = secrets.token_hex(16) + extension
        destination = MEDIA_DIR / filename
        try:
            with destination.open("xb") as handle:
                handle.write(data)
        except OSError:
            self.send_error(500)
            return
        body = ("/media/" + filename).encode("ascii")
        self.send_response(201)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self) -> None:
        self.send_error(405)

    def do_DELETE(self) -> None:
        self.send_error(405)


if __name__ == "__main__":
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    read_upload_token()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
