"""Refresh the long-lived Instagram Login token and replace its GitHub environment secret."""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

OWNER = "NetensAI"
REPOSITORY = "Funzug"
ENVIRONMENT = "funzug-publish"
SECRET_NAME = "FUNZUG_INSTAGRAM_ACCESS_TOKEN"
META_REFRESH_URL = "https://graph.instagram.com/refresh_access_token"
GITHUB_API = "https://api.github.com"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(request: Request) -> tuple[int, dict]:
    opener = build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=25) as response:
            status = response.status
            body = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"request failed with HTTP {exc.code}; response omitted") from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("request failed to connect or timed out") from None
    if not body:
        return status, {}
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("service returned an unreadable response") from None
    if not isinstance(payload, dict):
        raise RuntimeError("service returned an unexpected response")
    return status, payload


def meta_refresh(token: str) -> tuple[str, int]:
    query = urlencode({"grant_type": "ig_refresh_token", "access_token": token})
    request = Request(
        f"{META_REFRESH_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "FunzugPublisher/1.0"},
    )
    _, payload = request_json(request)
    refreshed = payload.get("access_token")
    expires_in = payload.get("expires_in")
    if not isinstance(refreshed, str) or not refreshed or not isinstance(expires_in, int) or expires_in < 30 * 86400:
        raise RuntimeError("Meta returned an invalid token refresh response")
    return refreshed, expires_in


def github_request(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{GITHUB_API}{path}",
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "FunzugPublisher/1.0",
        },
    )
    status, response = request_json(request)
    if not 200 <= status < 300:
        raise RuntimeError("GitHub secret update failed")
    return response


def github_installation_token(app_id: str, private_key: str) -> str:
    try:
        import jwt
    except ImportError:
        raise RuntimeError("GitHub App JWT dependency is unavailable") from None
    now = int(time.time())
    try:
        app_jwt = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": app_id},
            private_key.replace("\\n", "\n"),
            algorithm="RS256",
        )
    except Exception:
        raise RuntimeError("GitHub App authentication could not be created") from None
    installation = github_request(
        "GET", f"/repos/{OWNER}/{REPOSITORY}/installation", app_jwt
    )
    installation_id = installation.get("id")
    if not isinstance(installation_id, int):
        raise RuntimeError("GitHub App is not installed on the Funzug repository")
    token_response = github_request(
        "POST",
        f"/app/installations/{installation_id}/access_tokens",
        app_jwt,
        {"permissions": {"environments": "write"}},
    )
    installation_token = token_response.get("token")
    if not isinstance(installation_token, str) or not installation_token:
        raise RuntimeError("GitHub did not issue an installation token")
    return installation_token


def encrypt_secret_value(public_key_text: str, value: str) -> str:
    try:
        from nacl.public import PublicKey, SealedBox
    except ImportError:
        raise RuntimeError("GitHub secret-encryption dependency is unavailable") from None
    try:
        public_key = PublicKey(base64.b64decode(public_key_text, validate=True))
        encrypted = SealedBox(public_key).encrypt(value.encode())
    except (ValueError, TypeError):
        raise RuntimeError("GitHub environment public key could not be used") from None
    return base64.b64encode(encrypted).decode()


def replace_environment_secret(token: str, github_token: str) -> None:
    prefix = f"/repos/{OWNER}/{REPOSITORY}/environments/{ENVIRONMENT}/secrets"
    key = github_request("GET", f"{prefix}/public-key", github_token)
    key_text, key_id = key.get("key"), key.get("key_id")
    if not isinstance(key_text, str) or not isinstance(key_id, str):
        raise RuntimeError("GitHub returned an invalid environment public key")
    encrypted_value = encrypt_secret_value(key_text, token)
    github_request(
        "PUT",
        f"{prefix}/{SECRET_NAME}",
        github_token,
        {"encrypted_value": encrypted_value, "key_id": key_id},
    )


def main() -> int:
    instagram_token = os.environ.get(SECRET_NAME, "")
    app_id = os.environ.get("FUNZUG_GH_APP_ID", "")
    private_key = os.environ.get("FUNZUG_GH_APP_PRIVATE_KEY", "")
    app_secret = os.environ.get("FUNZUG_META_APP_SECRET", "")
    instagram_user_id = os.environ.get("FUNZUG_INSTAGRAM_USER_ID", "")
    graph_version = (os.environ.get("FUNZUG_META_GRAPH_VERSION") or "26.0").strip().removeprefix("v")
    api_mode = (os.environ.get("FUNZUG_INSTAGRAM_API_MODE") or "facebook_login").strip().lower()
    if api_mode != "instagram_login":
        print("Instagram token refresh skipped; FUNZUG_INSTAGRAM_API_MODE is not instagram_login")
        return 0
    if not all((instagram_token, app_id, private_key, app_secret, instagram_user_id)):
        print("Missing Instagram token, account ID, Meta app secret, or GitHub App credentials")
        return 1
    try:
        refreshed_token, expires_in = meta_refresh(instagram_token)
        from scripts.meta_token_diagnostic import APP_ID, INSTAGRAM_LOGIN_SCOPES, debug_token, summarize
        from scripts.verify_meta_credentials import verify_object

        app_access_token = f"{APP_ID}|{app_secret}"
        token_report, token_ready = summarize(
            debug_token(graph_version, app_access_token, refreshed_token),
            APP_ID,
            INSTAGRAM_LOGIN_SCOPES,
            allow_expiring=True,
        )
        if not token_ready:
            raise RuntimeError("refreshed Instagram token failed app, scope, validity, or lifetime checks")
        if not verify_object(graph_version, instagram_user_id, refreshed_token, "Refreshed Instagram account", "graph.instagram.com"):
            raise RuntimeError("refreshed Instagram token cannot access the configured account")
        installation_token = github_installation_token(app_id, private_key)
        replace_environment_secret(refreshed_token, installation_token)
    except RuntimeError as exc:
        print(f"Instagram token refresh failed: {exc}")
        return 1
    print(f"Instagram token refreshed, validated, and saved; lifetime_seconds={expires_in}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
