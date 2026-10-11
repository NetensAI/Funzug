"""Read-only check of a candidate Instagram Login token without logging it."""
from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from meta_token_diagnostic import INSTAGRAM_LOGIN_SCOPES, summarize

INSTAGRAM_APP_ID = "2556429418159496"


def inspect(token: str) -> tuple[str, str]:
    request = Request(
        "https://graph.instagram.com/me?fields=id,username",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"Instagram account check failed with HTTP {exc.code}; response omitted") from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise RuntimeError("Instagram account check could not be completed") from None
    if not isinstance(payload, dict):
        raise RuntimeError("Instagram returned an invalid account response")
    account_id, username = payload.get("id"), payload.get("username")
    if not isinstance(account_id, str) or not account_id.isdigit() or not isinstance(username, str):
        raise RuntimeError("Instagram returned an invalid account identity")
    return account_id, username


def inspect_lifetime(token: str, app_secret: str) -> tuple[dict, bool]:
    query = urlencode({
        "input_token": token,
        "access_token": f"{INSTAGRAM_APP_ID}|{app_secret}",
    })
    request = Request(
        f"https://graph.facebook.com/v26.0/debug_token?{query}",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"Instagram token inspection failed with HTTP {exc.code}; response omitted") from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise RuntimeError("Instagram token inspection could not be completed") from None
    return summarize(payload, INSTAGRAM_APP_ID, INSTAGRAM_LOGIN_SCOPES)


def main() -> int:
    token = os.environ.get("FUNZUG_INSTAGRAM_LOGIN_CANDIDATE_TOKEN", "")
    app_secret = os.environ.get("FUNZUG_INSTAGRAM_APP_SECRET", "")
    if not token:
        print("Candidate token is not configured")
        return 1
    if not app_secret:
        print("Instagram app secret is not configured")
        return 1
    try:
        account_id, username = inspect(token)
    except RuntimeError as exc:
        print(exc)
        return 1
    expected_id = "17841461799288910"
    expected_username = "funzugdotcom"
    matches = account_id == expected_id and username.lower() == expected_username
    print(f"Instagram Login candidate: account_match={matches}; account_id={account_id}; username={username}")
    try:
        summary, passed = inspect_lifetime(token, app_secret)
    except RuntimeError as exc:
        print(exc)
        return 1
    print(f"Token valid={summary['valid']}; app_match={summary['app_match']}; scopes={','.join(summary['scopes'])}")
    print(f"Missing scopes={','.join(summary['missing_scopes']) or '(none)'}")
    print(f"Expires at UTC={summary['expires_at']}; data access expires at UTC={summary['data_access_expires_at']}")
    return 0 if matches and passed else 1


if __name__ == "__main__":
    sys.exit(main())
