"""Upload one reviewed image to Funzug's self-hosted media origin."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from funzug_pipeline import image_size

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("media origin must be HTTPS and must not contain embedded credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("media origin must not contain query strings or fragments")
    return value.rstrip("/")


def upload(path: Path, origin: str, token: str) -> str:
    if not token:
        raise ValueError("FUNZUG_MEDIA_UPLOAD_TOKEN is not set")
    content_type = CONTENT_TYPES.get(path.suffix.lower())
    if not content_type:
        raise ValueError("image must be PNG or JPEG")
    if image_size(path) != (1080, 1350):
        raise ValueError("image must be exactly 1080x1350")
    data = path.read_bytes()
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("image is empty or exceeds the 12 MiB upload limit")
    request = urllib.request.Request(
        origin + "/upload",
        data=data,
        headers={"Authorization": "Bearer " + token.strip(), "Content-Type": content_type},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(RejectRedirects)
        with opener.open(request, timeout=30) as response:
            if response.status != 201:
                raise RuntimeError(f"media host returned HTTP {response.status}")
            media_path = response.read(200).decode("ascii").strip()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"media upload failed with HTTP {exc.code}; response omitted") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("media upload failed to connect or timed out") from None
    if not re.fullmatch(r"/media/[0-9a-f]{32}\.jpeg", media_path):
        raise RuntimeError("media host returned an invalid public path")
    return origin + media_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a reviewed image to the Funzug public media host")
    parser.add_argument("image", type=Path)
    parser.add_argument("--origin", default=os.environ.get("FUNZUG_MEDIA_BASE_URL", ""))
    parser.add_argument("--confirm-public-upload", choices=["FUNZUG"], required=True)
    args = parser.parse_args()
    try:
        origin = public_origin(args.origin)
        if not args.image.is_file():
            raise ValueError("image file does not exist")
        media_url = upload(args.image, origin, os.environ.get("FUNZUG_MEDIA_UPLOAD_TOKEN", ""))
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(media_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
