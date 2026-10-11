"""Read-only check that configured Meta tokens can access the expected objects."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def safe_meta_message(message: str) -> str:
    """Redact credentials and identifiers before emitting a short Meta error hint."""
    message = re.sub(r"(?i)(access_token|oauth_token|appsecret_proof)=([^&\s]+)", r"\1=[REDACTED]", message)
    message = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", message)
    message = re.sub(r"\bEA[A-Za-z0-9_-]{20,}\b", "[REDACTED_TOKEN]", message)
    message = re.sub(r"\b[A-Za-z0-9_-]{100,}\b", "[REDACTED_TOKEN]", message)
    message = re.sub(r"https?://\S+", "[URL]", message)
    message = re.sub(r"\b\d{10,}\b", "[ID]", message)
    return " ".join(message.split())[:180]

def normalize_graph_version(value: str | None) -> str:
    """Normalize an optional Actions variable, defaulting when it is empty."""
    return (value or "").strip().removeprefix("v") or "26.0"


def verify_object(
    graph_version: str,
    object_id: str,
    token: str,
    label: str,
    host: str = "graph.facebook.com",
) -> bool:
    if host not in {"graph.facebook.com", "graph.instagram.com"}:
        print(f"{label}: failed (Meta API host is not allowed)")
        return False
    query = urllib.parse.urlencode({"fields": "id"})
    url = f"https://{host}/v{graph_version}/{object_id}?{query}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            error_payload = json.loads(exc.read())
            details = error_payload.get("error", {})
        except (json.JSONDecodeError, OSError):
            details = {}
        safe_details = []
        if isinstance(details, dict):
            error_type = details.get("type")
            error_code = details.get("code")
            error_subcode = details.get("error_subcode")
            message = details.get("message", "")
            if isinstance(error_type, str) and error_type.isascii() and error_type.isalnum():
                safe_details.append(error_type)
            if isinstance(error_code, int):
                safe_details.append(f"code {error_code}")
            if isinstance(error_subcode, int):
                safe_details.append(f"subcode {error_subcode}")
            if isinstance(message, str):
                lowered = message.lower()
                if "active access token" in lowered:
                    safe_details.append("token missing or inactive")
                elif "access token" in lowered:
                    safe_details.append("token rejected")
                elif "permission" in lowered:
                    safe_details.append("permission rejected")
                elif "unsupported get request" in lowered:
                    safe_details.append("object ID or token cannot access this object")
        if isinstance(message, str) and message:
            safe_message = safe_meta_message(message)
            if safe_message:
                safe_details.append(f"Meta message: {safe_message}")
        trace_id = details.get("fbtrace_id") if isinstance(details, dict) else None
        if isinstance(trace_id, str) and trace_id.isascii() and trace_id.replace("_", "").isalnum():
            safe_details.append(f"trace {trace_id[:64]}")
        suffix = f", {', '.join(safe_details)}" if safe_details else ""
        print(f"{label}: failed (Meta returned HTTP {exc.code}{suffix})")
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

    version = normalize_graph_version(os.environ.get("FUNZUG_META_GRAPH_VERSION"))
    instagram_api_mode = (os.environ.get("FUNZUG_INSTAGRAM_API_MODE") or "facebook_login").strip().lower()
    if instagram_api_mode not in {"facebook_login", "instagram_login"}:
        print("FUNZUG_INSTAGRAM_API_MODE must be facebook_login or instagram_login")
        return 1
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
            "graph.instagram.com" if instagram_api_mode == "instagram_login" else "graph.facebook.com",
        ),
    ]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
