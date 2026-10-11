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
INSTAGRAM_LOGIN_SCOPES = {
    "instagram_business_basic",
    "instagram_business_content_publish",
}


def expiry_label(value: object) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return "never or not provided"
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def explicitly_non_expiring(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0


def expiry_is_active(value: object, now: float) -> bool:
    if explicitly_non_expiring(value):
        return True
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > now
    )


def summarize(
    payload: object,
    expected_app_id: str,
    required_scopes: set[str],
    now: float | None = None,
) -> tuple[dict, bool]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return {
            "valid": False,
            "app_match": False,
            "scopes": [],
            "missing_scopes": sorted(required_scopes),
            "expires_at": "unknown",
            "data_access_expires_at": "unknown",
            "explicitly_non_expiring": False,
            "lifetime_active": False,
        }, False
    data = payload["data"]
    scopes = sorted({scope for scope in data.get("scopes", []) if isinstance(scope, str)})
    app_match = str(data.get("app_id", "")) == expected_app_id
    valid = data.get("is_valid") is True
    missing = sorted(required_scopes - set(scopes))
    current_time = datetime.now(timezone.utc).timestamp() if now is None else now
    expires_at = data.get("expires_at")
    data_access_expires_at = data.get("data_access_expires_at")
    no_expiry = explicitly_non_expiring(expires_at) and explicitly_non_expiring(data_access_expires_at)
    lifetime_active = expiry_is_active(expires_at, current_time) and expiry_is_active(
        data_access_expires_at, current_time
    )
    result = {
        "valid": valid,
        "app_match": app_match,
        "scopes": scopes,
        "missing_scopes": missing,
        "expires_at": expiry_label(data.get("expires_at")),
        "data_access_expires_at": expiry_label(data.get("data_access_expires_at")),
        "explicitly_non_expiring": no_expiry,
        "lifetime_active": lifetime_active,
    }
    return result, valid and app_match and not missing and lifetime_active


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
    instagram_api_mode = (os.environ.get("FUNZUG_INSTAGRAM_API_MODE") or "facebook_login").strip().lower()
    graph_version = (os.environ.get("FUNZUG_META_GRAPH_VERSION") or "26.0").strip().removeprefix("v")
    if instagram_api_mode not in {"facebook_login", "instagram_login"}:
        print("FUNZUG_INSTAGRAM_API_MODE must be facebook_login or instagram_login")
        return 1
    if not app_secret or not page_token or not instagram_token:
        print("Missing required GitHub Actions secrets for read-only token diagnostics")
        return 1

    app_access_token = f"{APP_ID}|{app_secret}"
    checks = (
        ("Facebook Page token", page_token, PAGE_SCOPES),
        (
            "Instagram token",
            instagram_token,
            INSTAGRAM_LOGIN_SCOPES if instagram_api_mode == "instagram_login" else INSTAGRAM_SCOPES,
        ),
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
        print(f"  explicitly_non_expiring={summary['explicitly_non_expiring']}")
        if not summary["explicitly_non_expiring"] and summary["lifetime_active"]:
            print("  warning=finite-lifetime token; publishing will fail after either expiry")
        all_valid = all_valid and passed
    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
