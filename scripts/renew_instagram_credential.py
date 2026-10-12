"""Refresh and atomically save one encrypted GitHub environment secret."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta
import json
import os
import sys
import time
from zoneinfo import ZoneInfo
from urllib.request import Request

from instagram_credentials import decode_bundle, make_bundle, refresh_bundle, request_json, verify_account

OWNER = "NetensAI"
REPO = "Funzug"
ENVIRONMENT = "funzug-publish"
SECRET_NAME = "FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL"


def github(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    request = Request("https://api.github.com" + path,
        data=json.dumps(payload).encode() if payload is not None else None, method=method,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    # Secret update returns 204, without a JSON body.
    if method == "PUT":
        from urllib.error import HTTPError, URLError
        from urllib.request import build_opener
        from instagram_credentials import NoRedirect
        try:
            with build_opener(NoRedirect()).open(request, timeout=25) as response:
                if response.status not in (201, 204):
                    raise RuntimeError("GitHub secret update failed")
        except (HTTPError, URLError, TimeoutError, OSError):
            raise RuntimeError("GitHub secret update failed; details omitted") from None
        return {}
    return request_json(request)


def installation_token() -> str:
    import jwt
    now = int(time.time())
    try:
        signed = jwt.encode({"iat": now - 60, "exp": now + 540, "iss": os.environ["FUNZUG_GH_APP_ID"]},
                            os.environ["FUNZUG_GH_APP_PRIVATE_KEY"].replace("\\n", "\n"), algorithm="RS256")
    except Exception:
        raise RuntimeError("GitHub App authentication failed") from None
    installation = github("GET", f"/repos/{OWNER}/{REPO}/installation", signed)
    if type(installation.get("id")) is not int:
        raise RuntimeError("GitHub App is not installed on Funzug")
    response = github("POST", f"/app/installations/{installation['id']}/access_tokens", signed,
                      {"repositories": [REPO], "permissions": {"environments": "write"}})
    if not isinstance(response.get("token"), str) or not response["token"]:
        raise RuntimeError("GitHub installation authentication failed")
    return response["token"]


def save_secret(name: str, value: str, auth: str) -> None:
    from nacl.public import PublicKey, SealedBox
    if name not in {SECRET_NAME, "FUNZUG_GH_APP_ID", "FUNZUG_GH_APP_PRIVATE_KEY"}:
        raise RuntimeError("Secret name is outside the Funzug credential scope")
    path = f"/repos/{OWNER}/{REPO}/environments/{ENVIRONMENT}/secrets"
    key = github("GET", path + "/public-key", auth)
    try:
        encrypted = SealedBox(PublicKey(base64.b64decode(key["key"], validate=True))).encrypt(value.encode())
        key_id = key["key_id"]
    except Exception:
        raise RuntimeError("GitHub encryption key could not be used") from None
    github("PUT", path + "/" + name, auth,
           {"encrypted_value": base64.b64encode(encrypted).decode(), "key_id": key_id})


def save_bundle(bundle: dict, auth: str) -> None:
    save_secret(SECRET_NAME, json.dumps(bundle), auth)


def main() -> int:
    try:
        # Obtain the scoped GitHub writer before calling a token-refresh endpoint.
        auth = installation_token()
        raw = os.environ.get(SECRET_NAME, "")
        now = int(time.time())
        if os.environ.get("BOOTSTRAP_INSTAGRAM_LOGIN") == "true":
            if raw:
                raise RuntimeError("Bootstrap refused because a credential bundle already exists")
            token = os.environ.get("FUNZUG_INSTAGRAM_LOGIN_CANDIDATE_TOKEN", "")
            generation_time = datetime.fromisoformat(os.environ["CANDIDATE_GENERATED_AT"])
            if generation_time.utcoffset() != timedelta(hours=5, minutes=30):
                raise RuntimeError("Generation time must use IST +05:30")
            generated = generation_time.timestamp()
            if not token or not now - 86400 <= generated <= now:
                raise RuntimeError("Bootstrap requires a newly generated dashboard token and its generation time")
            account = verify_account(token)
            bundle = make_bundle(token, account, int(generated) + 300, int(generated) + 59 * 86400)
            decode_bundle(json.dumps(bundle), now)
        else:
            bundle = refresh_bundle(decode_bundle(raw, now), now)
        for attempt in range(3):
            try:
                save_bundle(bundle, auth)
                break
            except RuntimeError:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        expiry = datetime.fromtimestamp(bundle["expires_at"], ZoneInfo("Asia/Kolkata")).isoformat()
        print("Instagram credential validated and saved; expiry_IST=" + expiry)
        return 0
    except Exception:
        # Never expose exception strings from JWT, request URLs, or credential libraries.
        print("Instagram credential renewal failed. Existing saved credential was retained; inspect configuration and service availability.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
