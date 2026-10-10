"""Read-only Meta token introspection. Never print token values or raw API responses."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

APP_ID = "2180210799547573"
PAGE_SCOPES = {"pages_manage_posts", "pages_show_list", "pages_read_engagement"}
INSTAGRAM_SCOPES = {
    "instagram_content_publish",
    "instagram_basic",
    "pages_show_list",
    "pages_read_engagement",
}


def expiry_label(value: object) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return "never or not provided"
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def summarize(payload: object, expected_app_id: str, required_scopes: set[str]) -> tuple[dict, bool]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return {"valid": False, "app_match": False, "scopes": [], "missing_scopes": sorted(required_scopes), "expires_at": "unknown", "data_access_expires_at": "unknown"}, False
    data = payload["data"]
    scopes = sorted({scope for scope in data.get("scopes", []) if isinstance(scope, str)})
    app_match = str(data.get("app_id", "")) == expected_app_id
    valid = data.get("is_valid") is True
    missing = sorted(required_scopes - set(scopes))
    result = {
        "valid": valid,
        "app_match": app_match,
        "scopes": scopes,
        "missing_scopes": missing,
        "expires_at": expiry_label(data.get("expires_at")),
        "data_access_expires_at": expiry_label(data.get("data_access_expires_at")),
    }
    return result, valid and app_match and not missing


def debug_token(graph_version: str, app_access_token: str, input_token: str) -> object:
    query = urlencode({"input_token": input_token, "access_token": app_access_token})
    url = f"https://graph.facebook.com/v{graph_version}/debug_token?{query}"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        raise RuntimeError(f"Meta token-debug request failed with HTTP {exc.code}; response omitted") from None
    except (URLError, TimeoutError):
        raise RuntimeError("Meta token-debug request failed to connect or timed out") from None
    except (json.JSONDecodeError, OSError):
        raise RuntimeError("Meta token-debug returned an unreadable response") from None


def main() -> int:
    app_secret = os.environ.get("FUNZUG_META_APP_SECRET", "")
    page_token = os.environ.get("FUNZUG_FACEBOOK_PAGE_TOKEN", "")
    instagram_token = os.environ.get("FUNZUG_INSTAGRAM_ACCESS_TOKEN", "")
    graph_version = (os.environ.get("FUNZUG_META_GRAPH_VERSION") or "26.0").strip().removeprefix("v")
    if not app_secret or not page_token or not instagram_token:
        print("Missing required GitHub Actions secrets for read-only token diagnostics")
        return 1

    app_access_token = f"{APP_ID}|{app_secret}"
    checks = (
        ("Facebook Page token", page_token, PAGE_SCOPES),
        ("Instagram token", instagram_token, INSTAGRAM_SCOPES),
    )
    all_valid = True
    for label, token, required_scopes in checks:
        try:
            payload = debug_token(graph_version, app_access_token, token)
        except RuntimeError as exc:
            print(f"{label}: diagnostic failed ({exc})")
            all_valid = False
            continue
        summary, passed = summarize(payload, APP_ID, required_scopes)
        print(f"{label}: valid={summary['valid']}; app_match={summary['app_match']}")
        print(f"  scopes={', '.join(summary['scopes']) or '(none)'}")
        print(f"  missing_required_scopes={', '.join(summary['missing_scopes']) or '(none)'}")
        print(f"  expires_at_utc={summary['expires_at']}; data_access_expires_at_utc={summary['data_access_expires_at']}")
        all_valid = all_valid and passed
    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
