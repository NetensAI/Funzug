"""Read-only check that configured Meta tokens can access the expected objects."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def verify_object(graph_version: str, object_id: str, token: str, label: str) -> bool:
    url = f"https://graph.facebook.com/v{graph_version}/{object_id}?fields=id"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        print(f"{label}: failed (Meta returned HTTP {exc.code})")
        return False
    except (urllib.error.URLError, TimeoutError):
        print(f"{label}: failed (connection or timeout)")
        return False
    except (json.JSONDecodeError, OSError):
        print(f"{label}: failed (invalid response)")
        return False

    valid = isinstance(payload, dict) and str(payload.get("id", "")) == object_id
    print(f"{label}: {'valid' if valid else 'failed'}")
    return valid


def main() -> int:
    required = {
        "Facebook Page": ("FUNZUG_FACEBOOK_PAGE_ID", "FUNZUG_FACEBOOK_PAGE_TOKEN"),
        "Instagram account": ("FUNZUG_INSTAGRAM_USER_ID", "FUNZUG_INSTAGRAM_ACCESS_TOKEN"),
    }
    missing = [name for pair in required.values() for name in pair if not os.environ.get(name)]
    if missing:
        print("Missing required GitHub Actions secrets: " + ", ".join(missing))
        return 1

    version = os.environ.get("FUNZUG_META_GRAPH_VERSION", "26.0").strip().removeprefix("v")
    results = [
        verify_object(
            version,
            os.environ["FUNZUG_FACEBOOK_PAGE_ID"],
            os.environ["FUNZUG_FACEBOOK_PAGE_TOKEN"],
            "Facebook Page credential",
        ),
        verify_object(
            version,
            os.environ["FUNZUG_INSTAGRAM_USER_ID"],
            os.environ["FUNZUG_INSTAGRAM_ACCESS_TOKEN"],
            "Instagram credential",
        ),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
