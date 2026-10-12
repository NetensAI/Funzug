#!/usr/bin/env python3
"""Approval-gated image and carousel publishing for Funzug's Meta accounts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
QUEUE_PATH = ROOT / "queue.json"
DRAFT_QUEUE_PATH = ROOT / "drafts" / "queue.json"
HISTORY_PATH = ROOT / "history.json"
LOG_PATH = ROOT / "logs" / "events.jsonl"
REVIEW_CHECKS = ("claims", "sources", "caption", "images", "platforms", "schedule")
_configured_graph_version = os.getenv("FUNZUG_META_GRAPH_VERSION", "").strip().lower().removeprefix("v")
GRAPH_VERSION = f"v{_configured_graph_version or '26.0'}"
GRAPH_HOST = "graph.facebook.com"
INSTAGRAM_LOGIN_HOST = "graph.instagram.com"
INSTAGRAM_API_MODES = {"facebook_login", "instagram_login"}
CONTAINER_STATUS_ATTEMPTS = 12
CONTAINER_STATUS_INTERVAL = 5


def valid_review_checklist(value: Any) -> bool:
    """Accept legacy detailed reviews or BrandFlow's single explicit approval."""
    if not isinstance(value, dict):
        return False
    return (
        all(value.get(key) is True for key in REVIEW_CHECKS)
        or value.get("approvalConfirmed") is True
    )


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temp.replace(path)


def log_event(event: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"logged_at": iso_now(), **event}, ensure_ascii=False) + "\n")


def parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("scheduled_at must include a timezone offset")
    return parsed


def parse_schedule_time(value: str) -> dt.datetime:
    parsed = parse_time(value)
    if parsed.utcoffset() != dt.timedelta(hours=5, minutes=30):
        raise ValueError("scheduled_at must use IST (UTC+05:30)")
    return parsed


def https_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def safe_error_message(message: str) -> str:
    """Keep API diagnostics useful without persisting credentials or URL secrets."""
    message = re.sub(r"(?i)(access_token|oauth_token|appsecret_proof)=([^&\s]+)", r"\1=[REDACTED]", message)
    message = re.sub(r"\bEA[A-Za-z0-9]{20,}\b", "[REDACTED_TOKEN]", message)
    return message[:300]


def image_size(path: Path) -> tuple[int, int] | None:
    """Read PNG or JPEG dimensions without a third-party imaging package."""
    with path.open("rb") as handle:
        header = handle.read(32)
        if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
            return struct.unpack(">II", header[16:24])
        if not header.startswith(b"\xff\xd8"):
            return None
        handle.seek(2)
        while True:
            prefix = handle.read(1)
            if not prefix:
                return None
            if prefix != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if not marker:
                return None
            if marker in {b"\xd8", b"\xd9"}:
                continue
            length_bytes = handle.read(2)
            if len(length_bytes) != 2:
                return None
            length = struct.unpack(">H", length_bytes)[0]
            is_size_marker = marker[0] in (
                *range(0xC0, 0xC4), *range(0xC5, 0xC8),
                *range(0xC9, 0xCC), *range(0xCD, 0xD0),
            )
            if is_size_marker:
                data = handle.read(5)
                if len(data) == 5:
                    height, width = struct.unpack(">HH", data[1:5])
                    return width, height
                return None
            handle.seek(length - 2, os.SEEK_CUR)


def validate_item(
    item: dict[str, Any],
    required_size: tuple[int, int],
    require_public_media_url: bool = True,
) -> list[str]:
    errors: list[str] = []
    item_id = item.get("id", "<missing id>")
    if not isinstance(item_id, str) or not item_id.strip():
        errors.append("missing id")
    if item.get("status", "draft") not in {"draft", "approved", "published", "failed"}:
        errors.append("invalid status")
    approval = item.get("approval") if isinstance(item.get("approval"), dict) else {}
    if item.get("status") in {"approved", "published"} and approval.get("status") != "approved":
        errors.append("publishable status requires an approval record")
    if approval.get("status") == "approved":
        if not isinstance(approval.get("approved_by"), str) or not approval["approved_by"].strip():
            errors.append("approved item is missing approved_by")
        if not isinstance(approval.get("note"), str) or not approval["note"].strip():
            errors.append("approved item is missing its review note")
        checklist = approval.get("review_checklist")
        if not valid_review_checklist(checklist):
            errors.append("approved item requires review checklist checks or a single approval confirmation")
        try:
            parse_time(approval["approved_at"])
        except (KeyError, TypeError, ValueError):
            errors.append("approved item needs a timezone-aware approved_at")
    post_format = item.get("format")
    if post_format not in {"image", "carousel"}:
        errors.append("format must be image or carousel")
    platforms = item.get("platforms", [])
    if not isinstance(platforms, list):
        errors.append("platforms must be an array")
        platforms = []
    if not platforms:
        errors.append("missing platforms")
    if any(not isinstance(platform, str) or platform not in {"facebook", "instagram"} for platform in platforms):
        errors.append("platform must be facebook or instagram")
    if all(isinstance(platform, str) for platform in platforms) and len(set(platforms)) != len(platforms):
        errors.append("platforms contains duplicates")
    try:
        parse_schedule_time(item["scheduled_at"])
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"invalid scheduled_at: {exc}")
    for field in ("caption", "headline", "topic_key"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            errors.append(f"missing {field}")
    if post_format == "image":
        media_paths = [item.get("media_path")]
        media_url = item.get("public_media_url")
        media_urls = [media_url] if media_url is not None else None
        paths_field = "media_path"
        urls_field = "public_media_url"
    else:
        media_paths = item.get("media_paths")
        media_urls = item.get("public_media_urls")
        paths_field = "media_paths"
        urls_field = "public_media_urls"
        if not isinstance(media_paths, list) or not 2 <= len(media_paths) <= 10:
            errors.append("carousel media_paths must contain 2 to 10 images")
            media_paths = []
        if media_urls is not None and (not isinstance(media_urls, list) or not 2 <= len(media_urls) <= 10):
            errors.append("carousel public_media_urls must contain 2 to 10 URLs")
            media_urls = []
        if isinstance(media_urls, list) and isinstance(media_paths, list) and media_urls and len(media_urls) != len(media_paths):
            errors.append("carousel public_media_urls must match media_paths in length")
    if require_public_media_url and (
        not isinstance(media_urls, list)
        or len(media_urls) != len(media_paths)
        or not all(https_url(media_url) for media_url in media_urls)
    ):
        errors.append(f"{urls_field} must contain valid HTTPS URLs without embedded credentials")
    elif media_urls:
        for media_url in media_urls:
            if not https_url(media_url):
                errors.append(f"{urls_field} must contain valid HTTPS URLs without embedded credentials")
                continue
            parsed_url = urllib.parse.urlsplit(media_url)
            if parsed_url.query or parsed_url.fragment:
                errors.append(f"{urls_field} must not contain query strings or fragments")
    claims = item.get("claims", [])
    source_records = item.get("sources", [])
    if not isinstance(claims, list) or not isinstance(source_records, list):
        errors.append("claims and sources must be arrays")
        claims = []
        source_records = []
    sources = {
        source.get("id") for source in source_records
        if isinstance(source, dict) and isinstance(source.get("id"), str) and source.get("id")
    }
    if not claims:
        errors.append("at least one fact-checked claim is required")
    if not source_records:
        errors.append("at least one source is required")
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("claim records must be objects")
            continue
        if not isinstance(claim.get("text"), str) or not claim.get("text").strip():
            errors.append("claim is missing text")
        if not isinstance(claim.get("support_note"), str) or not claim["support_note"].strip():
            errors.append("claim needs a support_note explaining what the cited source establishes")
        source_refs = claim.get("source_ids")
        if (
            not isinstance(source_refs, list)
            or not source_refs
            or not all(isinstance(source_id, str) for source_id in source_refs)
            or not set(source_refs) <= sources
        ):
            errors.append(f"claim has missing or unknown source references: {claim.get('text', '')[:40]}")
    source_ids: set[str] = set()
    for source in source_records:
        if not isinstance(source, dict):
            errors.append("source records must be objects")
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            errors.append("source is missing an id")
        elif source_id in source_ids:
            errors.append(f"duplicate source id: {source_id}")
        if isinstance(source_id, str) and source_id:
            source_ids.add(source_id)
        if (
            not isinstance(source.get("title"), str) or not source["title"].strip()
            or not isinstance(source.get("publisher"), str) or not source["publisher"].strip()
        ):
            errors.append(f"source {source_id or '<missing>'} needs a title and publisher")
        if not https_url(source.get("url")):
            errors.append(f"source {source.get('id', '<missing>')} must be HTTPS")
        for field in ("published_at", "checked_at"):
            try:
                parse_time(source[field])
            except (KeyError, TypeError, ValueError):
                errors.append(f"source {source.get('id', '<missing>')} needs a timezone-aware {field}")
    if not media_paths or any(not isinstance(media_path, str) or not media_path for media_path in media_paths):
        errors.append(f"{paths_field} is required to verify each image is portrait 4:5")
    for media_path in media_paths:
        if not isinstance(media_path, str) or not media_path:
            continue
        path = (ROOT / media_path).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError:
            errors.append(f"{paths_field} must stay inside the repository")
        else:
            if not path.is_file():
                errors.append(f"image does not exist: {media_path}")
            else:
                try:
                    dimensions = image_size(path)
                except OSError as exc:
                    errors.append(f"could not read image: {exc}")
                else:
                    if not is_portrait_4_5(dimensions):
                        errors.append(f"media must be portrait 4:5 (for example 1080x1350), got {dimensions}")
    return errors


def is_portrait_4_5(dimensions: tuple[int, int]) -> bool:
    """Accept 4:5 with width rounded to the nearest whole pixel, without editing."""
    width, height = dimensions
    return 0 < width < height and abs(width * 5 - height * 4) <= 2


def validate_queue(queue: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_size = tuple(queue.get("brand", {}).get("required_image_size", [1080, 1350]))
    if required_size != (1080, 1350):
        errors.append("brand.required_image_size must be [1080, 1350]")
    topic_history = load_json(HISTORY_PATH).get("topic_keys", []) if HISTORY_PATH.exists() else []
    history = {topic for topic in topic_history if isinstance(topic, str)} if isinstance(topic_history, list) else set()
    seen_ids: set[str] = set()
    seen_topics: set[str] = set()
    for item in queue.get("items", []):
        if not isinstance(item, dict):
            errors.append("queue items must be objects")
            continue
        item_id = item.get("id", "<missing id>")
        topic_key = item.get("topic_key")
        if isinstance(item_id, str):
            if item_id in seen_ids:
                errors.append(f"duplicate item id: {item_id}")
            seen_ids.add(item_id)
        errors.extend(f"{item_id}: {error}" for error in validate_item(item, required_size))
        if isinstance(topic_key, str) and topic_key and topic_key in history and not any(isinstance(result, dict) and result.get("status") == "published" for result in (item.get("platform_results") or {}).values()) and item.get("status", "draft") in {"draft", "approved"}:
            errors.append(f"{item_id}: topic already appears in Meta history: {topic_key}")
        if isinstance(topic_key, str) and topic_key and topic_key in seen_topics:
            errors.append(f"{item_id}: topic_key duplicates another queue item: {topic_key}")
        if isinstance(topic_key, str) and topic_key:
            seen_topics.add(topic_key)
    return errors


def validate_draft_queue(queue: dict[str, Any]) -> list[str]:
    """Validate locally reviewable content drafts that do not have public media URLs yet."""
    errors: list[str] = []
    required_size = tuple(queue.get("brand", {}).get("required_image_size", [1080, 1350]))
    if required_size != (1080, 1350):
        errors.append("brand.required_image_size must be [1080, 1350]")
    items = queue.get("items", [])
    if not isinstance(items, list):
        return errors + ["draft items must be an array"]
    topic_history = load_json(HISTORY_PATH).get("topic_keys", []) if HISTORY_PATH.exists() else []
    history = {topic for topic in topic_history if isinstance(topic, str)} if isinstance(topic_history, list) else set()
    published_queue_items = load_json(QUEUE_PATH).get("items", []) if QUEUE_PATH.exists() else []
    previously_published_ids = {
        queue_item.get("id")
        for queue_item in published_queue_items
        if isinstance(queue_item, dict)
        and isinstance(queue_item.get("id"), str)
        and isinstance(queue_item.get("platform_results"), dict)
        and any(
            isinstance(result, dict) and result.get("status") == "published"
            for result in queue_item["platform_results"].values()
        )
    }
    seen_ids: set[str] = set()
    seen_topics: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            errors.append("draft items must be objects")
            continue
        item_id = item.get("id", "<missing id>")
        if item.get("status", "draft") != "draft":
            errors.append(f"{item_id}: draft inbox accepts draft status only")
        if isinstance(item.get("approval"), dict) and item["approval"].get("status") == "approved":
            errors.append(f"{item_id}: draft inbox must not contain an approval")
        topic_key = item.get("topic_key")
        if isinstance(item_id, str):
            if item_id in seen_ids:
                errors.append(f"{item_id}: duplicate draft id")
            seen_ids.add(item_id)
        errors.extend(
            f"{item_id}: {error}"
            for error in validate_item(item, required_size, require_public_media_url=False)
        )
        if isinstance(topic_key, str) and topic_key and topic_key in history and item_id not in previously_published_ids:
            errors.append(f"{item_id}: topic already appears in Meta history: {topic_key}")
        if isinstance(topic_key, str) and topic_key and topic_key in seen_topics:
            errors.append(f"{item_id}: topic_key duplicates another draft")
        if isinstance(topic_key, str) and topic_key:
            seen_topics.add(topic_key)
    return errors


def stage_draft(
    drafts: dict[str, Any],
    queue: dict[str, Any],
    item_id: str,
    public_media_url: str | list[str],
) -> None:
    """Copy a locally reviewed draft to the publish queue, without approving it."""
    draft_errors = validate_draft_queue(drafts)
    if draft_errors:
        raise RuntimeError("draft validation failed:\n" + "\n".join(draft_errors))
    candidate = next((item for item in drafts.get("items", []) if item.get("id") == item_id), None)
    if candidate is None:
        raise RuntimeError(f"draft not found: {item_id}")
    staged_item = json.loads(json.dumps(candidate))
    staged_item["status"] = "draft"
    media_urls = [public_media_url] if isinstance(public_media_url, str) else public_media_url
    if staged_item.get("format") == "carousel":
        staged_item["public_media_urls"] = media_urls
    elif len(media_urls) == 1:
        staged_item["public_media_url"] = media_urls[0]
    else:
        raise RuntimeError("single-image drafts require exactly one public media URL")
    staged_item.pop("approval", None)
    staged_queue = {**queue, "items": [*queue.get("items", []), staged_item]}
    queue_errors = validate_queue(staged_queue)
    if queue_errors:
        raise RuntimeError("publish queue validation failed:\n" + "\n".join(queue_errors))
    save_json(QUEUE_PATH, staged_queue)
    log_event({"event": "draft_staged", "item_id": item_id})
    print(f"staged {item_id} as an unapproved draft")


def host_and_approve_draft(
    drafts: dict[str, Any],
    queue: dict[str, Any],
    item_id: str,
    approved_by: str,
    note: str,
    review_checklist: dict[str, bool],
    media_origin: str,
    upload_token: str,
    public_upload_confirmation: str,
    publication_authorization: str,
    approved_at: str | None = None,
) -> None:
    """Upload reviewed draft media publicly, stage it, and record explicit approval."""
    if public_upload_confirmation != "FUNZUG":
        raise RuntimeError("explicit public-upload confirmation is required")
    if publication_authorization != "Yes, upload publicly and publish at scheduled time":
        raise RuntimeError("explicit publication authorization is required")
    if not valid_review_checklist(review_checklist):
        raise RuntimeError("approval requires explicit review checks or a single approval confirmation")
    if not approved_by.strip() or not note.strip():
        raise RuntimeError("approval requires a reviewer name and non-empty review note")

    draft_errors = validate_draft_queue(drafts)
    if draft_errors:
        raise RuntimeError("draft validation failed:\n" + "\n".join(draft_errors))
    queue_errors = validate_queue(queue)
    if queue_errors:
        raise RuntimeError("publish queue validation failed:\n" + "\n".join(queue_errors))
    if any(item.get("id") == item_id for item in queue.get("items", [])):
        raise RuntimeError(f"item {item_id} is already in the publishing queue")
    candidate = next((item for item in drafts.get("items", []) if item.get("id") == item_id), None)
    if candidate is None:
        raise RuntimeError(f"draft not found: {item_id}")
    if parse_schedule_time(candidate["scheduled_at"]).astimezone(dt.timezone.utc) <= dt.datetime.now(dt.timezone.utc):
        raise RuntimeError("scheduled_at must be in the future when the post is approved")
    if not upload_token:
        raise RuntimeError("FUNZUG_MEDIA_UPLOAD_TOKEN is not set")

    from scripts import upload_media

    origin = upload_media.public_origin(media_origin)
    media_paths = candidate.get("media_paths") if candidate.get("format") == "carousel" else [candidate["media_path"]]
    media_urls: list[str] = []
    try:
        for media_path in media_paths:
            path = (ROOT / media_path).resolve()
            media_urls.append(upload_media.upload(path, origin, upload_token))
    except Exception as exc:
        if media_urls:
            log_event({
                "event": "public_media_upload_incomplete",
                "item_id": item_id,
                "uploaded_media_urls": media_urls,
                "error": safe_error_message(str(exc)),
            })
        raise

    stage_draft(drafts, queue, item_id, media_urls)
    staged_queue = load_json(QUEUE_PATH)
    approve(staged_queue, item_id, approved_by, note, review_checklist, approved_at)


def api_post(path: str, form: dict[str, str], token: str, host: str = GRAPH_HOST) -> dict[str, Any]:
    if host not in {GRAPH_HOST, INSTAGRAM_LOGIN_HOST}:
        raise RuntimeError("Meta API host is not allowed")
    url = f"https://{host}/{GRAPH_VERSION}/{path.lstrip('/')}"
    payload = urllib.parse.urlencode({**form, "access_token": token}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            error = json.loads(body).get("error", {})
        except (json.JSONDecodeError, AttributeError):
            error = {}
        if not isinstance(error, dict):
            error = {}
        code = error.get("code")
        error_type = error.get("type")
        message = safe_error_message(str(error.get("message", "request failed")))
        details = ", ".join(str(value) for value in (error_type, code) if value is not None)
        raise RuntimeError(f"Meta API HTTP {exc.code}" + (f" ({details})" if details else "") + f": {message}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Meta API returned an invalid response")
    if "error" in result:
        error = result["error"]
        if not isinstance(error, dict):
            error = {}
        code = error.get("code")
        error_type = error.get("type")
        details = ", ".join(str(value) for value in (error_type, code) if value is not None)
        message = safe_error_message(str(error.get("message", "request failed")))
        raise RuntimeError("Meta API error" + (f" ({details})" if details else "") + f": {message}")
    return result


def api_get(
    path: str,
    token: str,
    params: dict[str, str] | None = None,
    host: str = GRAPH_HOST,
) -> dict[str, Any]:
    """Issue an authenticated read-only Graph API request without putting tokens in URLs."""
    if host not in {GRAPH_HOST, INSTAGRAM_LOGIN_HOST}:
        raise RuntimeError("Meta API host is not allowed")
    query = urllib.parse.urlencode(params or {})
    url = f"https://{host}/{GRAPH_VERSION}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            error = json.loads(body).get("error", {})
        except (json.JSONDecodeError, AttributeError):
            error = {}
        if not isinstance(error, dict):
            error = {}
        code = error.get("code")
        error_type = error.get("type")
        message = safe_error_message(str(error.get("message", "request failed")))
        details = ", ".join(str(value) for value in (error_type, code) if value is not None)
        raise RuntimeError(f"Meta API HTTP {exc.code}" + (f" ({details})" if details else "") + f": {message}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Meta API connection failed or timed out") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Meta API returned an invalid response")
    if "error" in result:
        error = result["error"]
        if not isinstance(error, dict):
            error = {}
        code = error.get("code")
        error_type = error.get("type")
        details = ", ".join(str(value) for value in (error_type, code) if value is not None)
        message = safe_error_message(str(error.get("message", "request failed")))
        raise RuntimeError("Meta API error" + (f" ({details})" if details else "") + f": {message}")
    return result


class MetaPublisher:
    def __init__(self) -> None:
        self.page_id = os.environ.get("FUNZUG_FACEBOOK_PAGE_ID")
        self.page_token = os.environ.get("FUNZUG_FACEBOOK_PAGE_TOKEN")
        self.ig_user_id = os.environ.get("FUNZUG_INSTAGRAM_USER_ID")
        self.ig_token = os.environ.get("FUNZUG_INSTAGRAM_ACCESS_TOKEN")
        self.ig_api_mode = (os.environ.get("FUNZUG_INSTAGRAM_API_MODE") or "facebook_login").strip().lower()
        if self.ig_api_mode not in INSTAGRAM_API_MODES:
            raise RuntimeError("FUNZUG_INSTAGRAM_API_MODE must be facebook_login or instagram_login")
        if self.ig_api_mode == "instagram_login":
            from instagram_credentials import decode_bundle
            credential = decode_bundle(os.environ.get("FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL", ""))
            self.ig_user_id = credential["account_id"]
            self.ig_token = credential["access_token"]
        self.ig_api_host = INSTAGRAM_LOGIN_HOST if self.ig_api_mode == "instagram_login" else GRAPH_HOST

    def facebook_page_token(self) -> str:
        """Derive and verify a Page token from the saved system user credential."""
        if not self.page_id or not self.page_token:
            raise RuntimeError("Facebook API environment is incomplete")
        if getattr(self, "_verified_page_token", None):
            return self._verified_page_token
        page = api_get(self.page_id, self.page_token, {"fields": "id,access_token"})
        if str(page.get("id")) != self.page_id:
            raise RuntimeError("Facebook Page token lookup returned the wrong Page")
        token = page.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Facebook Page access token is unavailable")
        identity = api_get("me", token, {"fields": "id"})
        if str(identity.get("id")) != self.page_id:
            raise RuntimeError("Facebook publishing token does not represent the configured Page")
        self._verified_page_token = token
        return token

    def publish_facebook_image(self, item: dict[str, Any]) -> dict[str, Any]:
        page_token = self.facebook_page_token()
        return api_post(f"{self.page_id}/photos", {"url": item["public_media_url"], "caption": item["caption"]}, page_token)

    def publish_facebook_carousel(self, item: dict[str, Any]) -> dict[str, Any]:
        page_token = self.facebook_page_token()
        media_ids = []
        for media_url in item["public_media_urls"]:
            photo = api_post(
                f"{self.page_id}/photos",
                {"url": media_url, "published": "false"},
                page_token,
            )
            photo_id = photo.get("id")
            if not photo_id:
                raise RuntimeError("Facebook photo response did not include an id")
            media_ids.append(photo_id)
        form = {"message": item["caption"]}
        form.update({
            f"attached_media[{index}]": json.dumps({"media_fbid": media_id}, separators=(",", ":"))
            for index, media_id in enumerate(media_ids)
        })
        return api_post(f"{self.page_id}/feed", form, page_token)

    def publish_instagram_image(self, item: dict[str, Any]) -> dict[str, Any]:
        if not self.ig_user_id or not self.ig_token:
            raise RuntimeError("Instagram API environment is incomplete")
        container = api_post(
            f"{self.ig_user_id}/media",
            {"image_url": item["public_media_url"], "caption": item["caption"]},
            self.ig_token,
            host=self.ig_api_host,
        )
        creation_id = container.get("id")
        if not creation_id:
            raise RuntimeError("Instagram container response did not include an id")
        self.wait_for_instagram_container(str(creation_id))
        return api_post(
            f"{self.ig_user_id}/media_publish",
            {"creation_id": creation_id},
            self.ig_token,
            host=self.ig_api_host,
        )

    def wait_for_instagram_container(self, creation_id: str) -> None:
        for attempt in range(CONTAINER_STATUS_ATTEMPTS):
            status = api_get(
                creation_id,
                self.ig_token,
                {"fields": "status_code"},
                host=self.ig_api_host,
            )
            status_code = status.get("status_code")
            if status_code == "FINISHED":
                return
            if status_code in {"ERROR", "EXPIRED", "PUBLISHED"}:
                raise RuntimeError(f"Instagram media container is not publishable ({status_code})")
            if status_code != "IN_PROGRESS":
                raise RuntimeError("Instagram media container returned an unknown status")
            if attempt + 1 < CONTAINER_STATUS_ATTEMPTS:
                time.sleep(CONTAINER_STATUS_INTERVAL)
        else:
            raise RuntimeError("Instagram media container did not finish processing before timeout")

    def publish_instagram_carousel(self, item: dict[str, Any]) -> dict[str, Any]:
        if not self.ig_user_id or not self.ig_token:
            raise RuntimeError("Instagram API environment is incomplete")
        children = []
        for media_url in item["public_media_urls"]:
            child = api_post(
                f"{self.ig_user_id}/media",
                {"image_url": media_url, "is_carousel_item": "true"},
                self.ig_token,
                host=self.ig_api_host,
            )
            child_id = child.get("id")
            if not child_id:
                raise RuntimeError("Instagram carousel child response did not include an id")
            self.wait_for_instagram_container(str(child_id))
            children.append(str(child_id))
        container = api_post(
            f"{self.ig_user_id}/media",
            {"media_type": "CAROUSEL", "children": ",".join(children), "caption": item["caption"]},
            self.ig_token,
            host=self.ig_api_host,
        )
        creation_id = container.get("id")
        if not creation_id:
            raise RuntimeError("Instagram carousel response did not include an id")
        self.wait_for_instagram_container(str(creation_id))
        return api_post(
            f"{self.ig_user_id}/media_publish",
            {"creation_id": creation_id},
            self.ig_token,
            host=self.ig_api_host,
        )


def approve(
    queue: dict[str, Any], item_id: str, approved_by: str, note: str,
    review_checklist: dict[str, bool], approved_at: str | None = None,
) -> None:
    errors = validate_queue(queue)
    if errors:
        raise RuntimeError("queue validation failed:\n" + "\n".join(errors))
    for item in queue.get("items", []):
        if item.get("id") == item_id:
            if item.get("status", "draft") != "draft":
                raise RuntimeError(f"item {item_id} is not a draft")
            if parse_schedule_time(item["scheduled_at"]).astimezone(dt.timezone.utc) <= dt.datetime.now(dt.timezone.utc):
                raise RuntimeError("scheduled_at must be in the future when the post is approved")
            if not approved_by.strip():
                raise RuntimeError("approval requires a reviewer name")
            if not note.strip():
                raise RuntimeError("approval requires a non-empty review note")
            if not valid_review_checklist(review_checklist):
                raise RuntimeError("approval requires explicit review checks or a single approval confirmation")
            item["status"] = "approved"
            approval_time = approved_at or iso_now()
            parse_time(approval_time)
            item["approval"] = {
                "status": "approved", "approved_by": approved_by, "approved_at": approval_time, "note": note,
                "review_checklist": dict(review_checklist),
            }
            save_json(QUEUE_PATH, queue)
            log_event({"event": "approved", "item_id": item_id, "approved_by": approved_by})
            print(f"approved {item_id}")
            return
    raise RuntimeError(f"item not found: {item_id}")


def publish_due(queue: dict[str, Any], execute: bool, confirmation: str | None, item_id: str | None = None) -> int:
    errors = validate_queue(queue)
    if errors:
        raise RuntimeError("queue validation failed:\n" + "\n".join(errors))
    current = dt.datetime.now(dt.timezone.utc)
    due = [item for item in queue.get("items", []) if item.get("status") == "approved" and (item_id is None or item.get("id") == item_id) and parse_schedule_time(item["scheduled_at"]).astimezone(dt.timezone.utc) <= current]
    if not due:
        print("no approved items are due")
        return 0
    if not execute:
        for item in due:
            print(f"DRY RUN {item['id']}: {', '.join(item['platforms'])} {item['scheduled_at']}")
        return 0
    if confirmation != "FUNZUG":
        raise RuntimeError("publishing requires --confirm-publish FUNZUG")
    publisher = MetaPublisher()
    batch_success = True
    history = load_json(HISTORY_PATH) if HISTORY_PATH.exists() else {"checked_at": None, "source": "Funzug publishing workflow", "topic_keys": []}
    topic_keys = history.get("topic_keys", [])
    known_topics = {topic for topic in topic_keys if isinstance(topic, str)} if isinstance(topic_keys, list) else set()
    for item in due:
        platform_results = item.setdefault("platform_results", {})
        all_success = True
        for platform in item["platforms"]:
            try:
                post_format = item.get("format")
                if platform == "facebook":
                    result = publisher.publish_facebook_carousel(item) if post_format == "carousel" else publisher.publish_facebook_image(item)
                else:
                    result = publisher.publish_instagram_carousel(item) if post_format == "carousel" else publisher.publish_instagram_image(item)
                published_at = iso_now()
                result_id = result.get("post_id") or result.get("id")
                platform_results[platform] = {"status": "published", "published_at": published_at, "post_id": result_id}
                log_event({"event": "published", "item_id": item["id"], "platform": platform, "post_id": result_id})
                if item.get("topic_key"):
                    known_topics.add(item["topic_key"])
            except Exception as exc:
                all_success = False
                safe_message = safe_error_message(str(exc))
                platform_results[platform] = {"status": "failed", "failed_at": iso_now(), "error": safe_message}
                log_event({"event": "publish_failed", "item_id": item["id"], "platform": platform, "error": safe_message})
        item["status"] = "published" if all_success else "failed"
        item["last_attempt_at"] = iso_now()
        batch_success = batch_success and all_success
    save_json(QUEUE_PATH, queue)
    history["checked_at"] = iso_now()
    history["topic_keys"] = sorted(known_topics)
    save_json(HISTORY_PATH, history)
    return 0 if batch_success else 1


def retry_failed_facebook(queue: dict[str, Any], item_id: str) -> int:
    """Retry one explicitly authorized failed Facebook post through the normal publisher."""
    errors = validate_queue(queue)
    if errors:
        raise RuntimeError("queue validation failed:\n" + "\n".join(errors))
    item = next((row for row in queue.get("items", []) if row.get("id") == item_id), None)
    if item is None or item.get("status") != "failed" or item.get("platforms") != ["facebook"]:
        raise RuntimeError("retry requires one failed Facebook-only queue item")
    results = item.get("platform_results", {})
    if results.get("facebook", {}).get("status") != "failed":
        raise RuntimeError("Facebook retry requires a recorded failed attempt")
    approval = item.get("approval", {})
    authorizations = approval.get("retry_authorizations", []) if isinstance(approval, dict) else []
    if not any(
        isinstance(entry, dict)
        and entry.get("authorized_by") == "owner"
        and entry.get("platforms") == ["facebook"]
        and entry.get("topic_key") == item.get("topic_key")
        for entry in authorizations
    ):
        raise RuntimeError("Facebook retry lacks explicit owner authorization")
    if parse_schedule_time(item["scheduled_at"]).astimezone(dt.timezone.utc) > dt.datetime.now(dt.timezone.utc):
        raise RuntimeError("Facebook retry is not due")
    MetaPublisher().facebook_page_token()
    item["status"] = "approved"
    log_event({"event": "retry_started", "item_id": item_id, "platform": "facebook"})
    return publish_due(queue, True, "FUNZUG", item_id=item_id)


def has_due_approved_items(queue: dict[str, Any]) -> bool:
    errors = validate_queue(queue)
    if errors:
        raise RuntimeError("queue validation failed:\n" + "\n".join(errors))
    current = dt.datetime.now(dt.timezone.utc)
    return any(
        item.get("status") == "approved"
        and parse_schedule_time(item["scheduled_at"]).astimezone(dt.timezone.utc) <= current
        for item in queue.get("items", [])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Approval-gated Funzug publisher")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("validate-drafts", help="validate locally reviewable draft content and images")
    stage_parser = subparsers.add_parser("stage-draft", help="copy a draft with a public image URL into the unapproved publish queue")
    stage_parser.add_argument("--id", required=True)
    stage_parser.add_argument(
        "--public-media-url", action="append", required=True,
        help="repeat once per image in a carousel; provide one URL for a single-image post",
    )
    host_approve_parser = subparsers.add_parser(
        "host-and-approve-draft",
        help="upload a reviewed draft image publicly and approve it for its scheduled publication",
    )
    host_approve_parser.add_argument("--id", required=True)
    host_approve_parser.add_argument("--approved-by", required=True)
    host_approve_parser.add_argument("--note", required=True)
    host_approve_parser.add_argument("--media-origin", default=os.environ.get("FUNZUG_MEDIA_BASE_URL", ""))
    host_approve_parser.add_argument("--confirm-public-upload", choices=["FUNZUG"], required=True)
    host_approve_parser.add_argument(
        "--authorize-publication", choices=["Yes, upload publicly and publish at scheduled time"], required=True,
    )
    for check in REVIEW_CHECKS:
        host_approve_parser.add_argument(f"--review-{check}", action="store_true", required=True)
    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("--id", required=True)
    approve_parser.add_argument("--approved-by", required=True)
    approve_parser.add_argument("--note", default="")
    for check in REVIEW_CHECKS:
        approve_parser.add_argument(f"--review-{check}", action="store_true", help=f"attest that {check} were reviewed")
    publish_parser = subparsers.add_parser("publish-due")
    publish_parser.add_argument("--execute", action="store_true")
    publish_parser.add_argument("--confirm-publish")
    retry_parser = subparsers.add_parser("retry-failed-facebook", help="retry one owner-authorized failed Facebook post")
    retry_parser.add_argument("--id", required=True)
    subparsers.add_parser("check-due", help="print true only when an approved post is due")
    args = parser.parse_args()
    try:
        if args.command == "validate-drafts":
            drafts = load_json(DRAFT_QUEUE_PATH)
            errors = validate_draft_queue(drafts)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print(f"valid draft inbox: {len(drafts.get('items', []))} item(s)")
            return 0
        if args.command == "stage-draft":
            drafts = load_json(DRAFT_QUEUE_PATH)
            queue = load_json(QUEUE_PATH)
            stage_draft(drafts, queue, args.id, args.public_media_url)
            return 0
        if args.command == "host-and-approve-draft":
            drafts = load_json(DRAFT_QUEUE_PATH)
            queue = load_json(QUEUE_PATH)
            checklist = {key: getattr(args, f"review_{key}") for key in REVIEW_CHECKS}
            host_and_approve_draft(
                drafts,
                queue,
                args.id,
                args.approved_by,
                args.note,
                checklist,
                args.media_origin,
                os.environ.get("FUNZUG_MEDIA_UPLOAD_TOKEN", ""),
                args.confirm_public_upload,
                args.authorize_publication,
            )
            return 0
        queue = load_json(QUEUE_PATH)
        if args.command == "validate":
            errors = validate_queue(queue)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print(f"valid queue: {len(queue.get('items', []))} item(s)")
            return 0
        if args.command == "retry-failed-facebook":
            return retry_failed_facebook(queue, args.id)
        if args.command == "check-due":
            print("true" if has_due_approved_items(queue) else "false")
            return 0
        if args.command == "approve":
            checklist = {key: getattr(args, f"review_{key}") for key in REVIEW_CHECKS}
            approve(queue, args.id, args.approved_by, args.note, checklist)
            return 0
        return publish_due(queue, args.execute, args.confirm_publish)
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
