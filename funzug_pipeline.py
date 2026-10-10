#!/usr/bin/env python3
"""Approval-gated single-image publishing for Funzug's Meta accounts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
QUEUE_PATH = ROOT / "queue.json"
HISTORY_PATH = ROOT / "history.json"
LOG_PATH = ROOT / "logs" / "events.jsonl"
GRAPH_VERSION = os.getenv("FUNZUG_META_GRAPH_VERSION", "v26.0")


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


def validate_item(item: dict[str, Any], required_size: tuple[int, int]) -> list[str]:
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
        try:
            parse_time(approval["approved_at"])
        except (KeyError, TypeError, ValueError):
            errors.append("approved item needs a timezone-aware approved_at")
    if item.get("format") != "image":
        errors.append("only single-image posts are currently supported")
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
        parse_time(item["scheduled_at"])
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"invalid scheduled_at: {exc}")
    for field in ("caption", "headline", "topic_key"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            errors.append(f"missing {field}")
    media_url = item.get("public_media_url")
    if not https_url(media_url):
        errors.append("public_media_url must be a valid HTTPS URL without embedded credentials")
    elif urllib.parse.urlsplit(media_url).query or urllib.parse.urlsplit(media_url).fragment:
        errors.append("public_media_url must not contain query strings or fragments")
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
    media_path = item.get("media_path")
    if not isinstance(media_path, str) or not media_path:
        errors.append("media_path is required to verify the final image is exactly 1080x1350")
    else:
        path = (ROOT / media_path).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError:
            errors.append("media_path must stay inside the repository")
        else:
            if not path.is_file():
                errors.append(f"media_path does not exist: {media_path}")
            else:
                try:
                    dimensions = image_size(path)
                except OSError as exc:
                    errors.append(f"could not read media_path: {exc}")
                else:
                    if dimensions != required_size:
                        errors.append(f"media must be {required_size[0]}x{required_size[1]}, got {dimensions}")
    return errors


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
        if isinstance(topic_key, str) and topic_key and topic_key in history and item.get("status", "draft") in {"draft", "approved"}:
            errors.append(f"{item_id}: topic already appears in Meta history: {topic_key}")
        if isinstance(topic_key, str) and topic_key and topic_key in seen_topics:
            errors.append(f"{item_id}: topic_key duplicates another queue item: {topic_key}")
        if isinstance(topic_key, str) and topic_key:
            seen_topics.add(topic_key)
    return errors


def api_post(path: str, form: dict[str, str], token: str) -> dict[str, Any]:
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{path.lstrip('/')}"
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


class MetaPublisher:
    def __init__(self) -> None:
        self.page_id = os.environ.get("FUNZUG_FACEBOOK_PAGE_ID")
        self.page_token = os.environ.get("FUNZUG_FACEBOOK_PAGE_TOKEN")
        self.ig_user_id = os.environ.get("FUNZUG_INSTAGRAM_USER_ID")
        self.ig_token = os.environ.get("FUNZUG_INSTAGRAM_ACCESS_TOKEN")

    def publish_facebook_image(self, item: dict[str, Any]) -> dict[str, Any]:
        if not self.page_id or not self.page_token:
            raise RuntimeError("Facebook API environment is incomplete")
        return api_post(f"{self.page_id}/photos", {"url": item["public_media_url"], "caption": item["caption"]}, self.page_token)

    def publish_instagram_image(self, item: dict[str, Any]) -> dict[str, Any]:
        if not self.ig_user_id or not self.ig_token:
            raise RuntimeError("Instagram API environment is incomplete")
        container = api_post(f"{self.ig_user_id}/media", {"image_url": item["public_media_url"], "caption": item["caption"]}, self.ig_token)
        creation_id = container.get("id")
        if not creation_id:
            raise RuntimeError("Instagram container response did not include an id")
        return api_post(f"{self.ig_user_id}/media_publish", {"creation_id": creation_id}, self.ig_token)


def approve(queue: dict[str, Any], item_id: str, approved_by: str, note: str) -> None:
    errors = validate_queue(queue)
    if errors:
        raise RuntimeError("queue validation failed:\n" + "\n".join(errors))
    for item in queue.get("items", []):
        if item.get("id") == item_id:
            if item.get("status", "draft") != "draft":
                raise RuntimeError(f"item {item_id} is not a draft")
            if parse_time(item["scheduled_at"]).astimezone(dt.timezone.utc) <= dt.datetime.now(dt.timezone.utc):
                raise RuntimeError("scheduled_at must be in the future when the post is approved")
            if not approved_by.strip():
                raise RuntimeError("approval requires a reviewer name")
            if not note.strip():
                raise RuntimeError("approval requires a non-empty review note")
            item["status"] = "approved"
            item["approval"] = {"status": "approved", "approved_by": approved_by, "approved_at": iso_now(), "note": note}
            save_json(QUEUE_PATH, queue)
            log_event({"event": "approved", "item_id": item_id, "approved_by": approved_by})
            print(f"approved {item_id}")
            return
    raise RuntimeError(f"item not found: {item_id}")


def publish_due(queue: dict[str, Any], execute: bool, confirmation: str | None) -> int:
    errors = validate_queue(queue)
    if errors:
        raise RuntimeError("queue validation failed:\n" + "\n".join(errors))
    current = dt.datetime.now(dt.timezone.utc)
    due = [item for item in queue.get("items", []) if item.get("status") == "approved" and parse_time(item["scheduled_at"]).astimezone(dt.timezone.utc) <= current]
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
                result = publisher.publish_facebook_image(item) if platform == "facebook" else publisher.publish_instagram_image(item)
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


def has_due_approved_items(queue: dict[str, Any]) -> bool:
    errors = validate_queue(queue)
    if errors:
        raise RuntimeError("queue validation failed:\n" + "\n".join(errors))
    current = dt.datetime.now(dt.timezone.utc)
    return any(
        item.get("status") == "approved"
        and parse_time(item["scheduled_at"]).astimezone(dt.timezone.utc) <= current
        for item in queue.get("items", [])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Approval-gated Funzug publisher")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("--id", required=True)
    approve_parser.add_argument("--approved-by", required=True)
    approve_parser.add_argument("--note", default="")
    publish_parser = subparsers.add_parser("publish-due")
    publish_parser.add_argument("--execute", action="store_true")
    publish_parser.add_argument("--confirm-publish")
    subparsers.add_parser("check-due", help="print true only when an approved post is due")
    args = parser.parse_args()
    queue = load_json(QUEUE_PATH)
    try:
        if args.command == "validate":
            errors = validate_queue(queue)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print(f"valid queue: {len(queue.get('items', []))} item(s)")
            return 0
        if args.command == "check-due":
            print("true" if has_due_approved_items(queue) else "false")
            return 0
        if args.command == "approve":
            approve(queue, args.id, args.approved_by, args.note)
            return 0
        return publish_due(queue, args.execute, args.confirm_publish)
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
