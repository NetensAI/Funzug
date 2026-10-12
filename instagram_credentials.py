"""Instagram Login credentials, validated without creating public media."""
from __future__ import annotations

import hashlib
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

APP_ID = "2556429418159496"
USERNAME = "funzugdotcom"
REQUIRED_SCOPES = {"instagram_business_basic", "instagram_business_content_publish"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(request: Request) -> dict:
    try:
        with build_opener(NoRedirect()).open(request, timeout=25) as response:
            data = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"Credential service returned HTTP {exc.code}; response omitted") from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise RuntimeError("Credential service request failed; details omitted") from None
    if not isinstance(data, dict) or "error" in data:
        raise RuntimeError("Credential service returned an invalid response")
    return data


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def decode_bundle(raw: str, now: int | None = None) -> dict:
    try:
        bundle = json.loads(raw)
    except (ValueError, TypeError):
        raise RuntimeError("Instagram credential bundle is unavailable or invalid") from None
    current = int(time.time()) if now is None else now
    if not isinstance(bundle, dict):
        raise RuntimeError("Instagram credential bundle is invalid")
    token = bundle.get("access_token")
    account = bundle.get("account_id")
    expires = bundle.get("expires_at")
    refreshed = bundle.get("refreshed_at")
    if (
        bundle.get("version") != 1 or bundle.get("app_id") != APP_ID
        or bundle.get("username") != USERNAME
        or not isinstance(token, str) or not token
        or not isinstance(account, str) or not account.isdigit()
        or type(expires) is not int or expires <= current + 300
        or type(refreshed) is not int or refreshed > current + 300
        or expires > refreshed + 61 * 86400
        or bundle.get("token_fingerprint") != fingerprint(token)
        or not REQUIRED_SCOPES.issubset(set(bundle.get("verified_scopes", [])))
    ):
        raise RuntimeError("Instagram credential identity, lifetime, or integrity check failed")
    return bundle


def verify_account(token: str, expected_id: str | None = None) -> str:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    account = request_json(Request("https://graph.instagram.com/v26.0/me?fields=id,username", headers=headers))
    account_id = account.get("id")
    if (
        not isinstance(account_id, str) or not account_id.isdigit()
        or account.get("username", "").lower() != USERNAME
        or (expected_id is not None and account_id != expected_id)
    ):
        raise RuntimeError("Instagram credential does not represent Funzug")
    quota = request_json(Request(
        f"https://graph.instagram.com/v26.0/{account_id}/content_publishing_limit?fields=quota_usage,config",
        headers=headers,
    ))
    rows = quota.get("data")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict) or type(rows[0].get("quota_usage")) is not int:
        raise RuntimeError("Instagram publishing permission check failed")
    return account_id


def make_bundle(token: str, account_id: str, refreshed_at: int, expires_at: int) -> dict:
    return {
        "version": 1, "app_id": APP_ID, "username": USERNAME,
        "account_id": account_id, "access_token": token,
        "refreshed_at": refreshed_at, "expires_at": expires_at,
        "token_fingerprint": fingerprint(token), "verified_scopes": sorted(REQUIRED_SCOPES),
    }


def refresh_bundle(bundle: dict, now: int | None = None) -> dict:
    current = int(time.time()) if now is None else now
    bundle = decode_bundle(json.dumps(bundle), current)
    if current - bundle["refreshed_at"] < 25 * 3600:
        raise RuntimeError("Instagram token must be at least 25 hours old before refresh")
    query = urlencode({"grant_type": "ig_refresh_token", "access_token": bundle["access_token"]})
    result = request_json(Request(f"https://graph.instagram.com/refresh_access_token?{query}"))
    token, lifetime = result.get("access_token"), result.get("expires_in")
    if not isinstance(token, str) or not token or type(lifetime) is not int or not 30 * 86400 <= lifetime <= 61 * 86400:
        raise RuntimeError("Instagram returned an invalid refresh lifetime")
    account_id = verify_account(token, bundle["account_id"])
    return make_bundle(token, account_id, current, current + lifetime - 300)
