"""Read-only check of a candidate Instagram Login token without logging it."""
from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


def main() -> int:
    token = os.environ.get("FUNZUG_INSTAGRAM_LOGIN_CANDIDATE_TOKEN", "")
    if not token:
        print("Candidate token is not configured")
        return 1
    try:
        account_id, username = inspect(token)
    except RuntimeError as exc:
        print(exc)
        return 1
    expected_username = "funzugdotcom"
    matches = username.lower() == expected_username
    print(f"Instagram Login candidate: account_match={matches}; app_scoped_account_id={account_id}; username={username}")
    print("Token lifetime and publish scope are not inferred from this account-read check")
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
