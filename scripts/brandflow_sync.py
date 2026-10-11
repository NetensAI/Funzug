#!/usr/bin/env python3
"""Sync review-only Funzug drafts with BrandFlow and consume explicit approvals."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import funzug_pipeline as pipeline


DEFAULT_API = "https://funzug.netens.top/api/integrations/funzug/drafts"
BATCH_ID = "funzug-draft-inbox-v1"
SCHEDULE_TIMEZONE = ZoneInfo("Asia/Kolkata")
BRANDFLOW_CHECKS = (
    "factualAccuracy", "sourcesVerified", "imageReviewed", "captionReviewed",
    "scheduleReviewed", "rightsConfirmed", "finalAuthorization",
)


def api_request(method: str, url: str, secret: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Authorization", "Bearer " + secret)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"BrandFlow API returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError("BrandFlow API request failed") from None
    if not isinstance(result, dict):
        raise RuntimeError("BrandFlow API returned an invalid response")
    return result


def api_url() -> str:
    value = os.environ.get("FUNZUG_BRANDFLOW_DRAFTS_URL", DEFAULT_API).rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("BrandFlow draft API URL must be HTTPS without credentials, query, or fragment")
    return value


def secret() -> str:
    value = os.environ.get("FUNZUG_DRAFT_INGEST_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("FUNZUG_DRAFT_INGEST_SECRET is not configured")
    return value


def api_status(base_url: str, token: str) -> dict[str, dict[str, Any]]:
    url = base_url + "?" + urllib.parse.urlencode({"batchId": BATCH_ID})
    data = api_request("GET", url, token)
    rows = data.get("drafts")
    if not isinstance(rows, list):
        raise RuntimeError("BrandFlow status response is invalid")
    return {row["externalId"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("externalId"), str)}


def payload_for(item: dict[str, Any]) -> dict[str, Any]:
    relpath = item.get("media_path")
    if not isinstance(relpath, str) or item.get("format") != "image":
        raise ValueError(f"{item.get('id', '<unknown>')}: only single-image drafts are supported by this integration")
    path = (ROOT / relpath).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError:
        raise ValueError("draft image path must stay inside the repository") from None
    if not path.is_file() or pipeline.image_size(path) != (1080, 1350):
        raise ValueError(f"{item.get('id', '<unknown>')}: image is missing or not 1080x1350")
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in {"image/png", "image/jpeg"}:
        raise ValueError("draft image must be PNG or JPEG")
    sources = item.get("sources", [])
    claims = item.get("claims", [])
    source_urls = [source["url"] for source in sources]
    schedule = pipeline.parse_time(item["scheduled_at"]).astimezone(SCHEDULE_TIMEZONE)
    return {
        "schemaVersion": 1,
        "brandSlug": "funzug",
        "batchId": BATCH_ID,
        "drafts": [{
            "externalId": item["id"],
            "headline": item["headline"],
            "caption": item["caption"],
            "claims": [{
                "text": claim["text"],
                "source_ids": claim["source_ids"],
                "support_note": claim["support_note"],
            } for claim in claims],
            "sources": [{
                "id": source["id"],
                "title": source["title"],
                "publisher": source["publisher"],
                "url": source["url"],
                "published_at": source["published_at"],
                "checked_at": source["checked_at"],
            } for source in sources],
            "platforms": item["platforms"],
            "proposedSchedule": schedule.isoformat(),
            "scheduleTimezone": "Asia/Kolkata",
            "image": {
                "kind": "base64",
                "mimeType": mime,
                "width": 1080,
                "height": 1350,
                "data": base64.b64encode(path.read_bytes()).decode("ascii"),
            },
        }],
    }


def sync_pending() -> int:
    token, base = secret(), api_url()
    errors = pipeline.validate_draft_queue(pipeline.load_json(pipeline.DRAFT_QUEUE_PATH))
    if errors:
        raise RuntimeError("draft validation failed:\n" + "\n".join(errors))
    inbox = pipeline.load_json(pipeline.DRAFT_QUEUE_PATH)
    known = api_status(base, token)
    sent = 0
    for item in inbox["items"]:
        item_id = item["id"]
        if item_id in known:
            continue
        api_request("POST", base, token, payload_for(item))
        sent += 1
    print(f"BrandFlow sync complete: {sent} new draft(s) sent")
    return 0


def process_approvals() -> int:
    token, base = secret(), api_url()
    statuses = api_status(base, token)
    drafts = pipeline.load_json(pipeline.DRAFT_QUEUE_PATH)
    queue = pipeline.load_json(pipeline.QUEUE_PATH)
    local = {item["id"]: item for item in drafts.get("items", [])}
    completed = 0
    for item_id, status in statuses.items():
        if status.get("status") != "approved":
            continue
        if status.get("publicationAuthorized") is not True:
            raise RuntimeError(f"{item_id}: BrandFlow approval is missing explicit publication authorization")
        if any(item.get("id") == item_id for item in queue.get("items", [])):
            continue
        item = local.get(item_id)
        if not item or item.get("status") != "draft":
            raise RuntimeError(f"{item_id}: approved post is absent from the local draft inbox")
        checks = status.get("reviewChecks")
        if not isinstance(checks, dict) or any(checks.get(key) is not True for key in BRANDFLOW_CHECKS):
            raise RuntimeError(f"{item_id}: BrandFlow approval checklist is incomplete")
        reviewer = status.get("reviewedBy")
        note = status.get("reviewNote")
        if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(note, str) or not note.strip():
            raise RuntimeError(f"{item_id}: approval is missing reviewer identity or note")
        checklist = {key: True for key in pipeline.REVIEW_CHECKS}
        checklist["claims"] = checks["factualAccuracy"]
        checklist["sources"] = checks["sourcesVerified"]
        checklist["images"] = checks["imageReviewed"]
        checklist["caption"] = checks["captionReviewed"]
        checklist["platforms"] = checks["scheduleReviewed"]
        checklist["schedule"] = checks["scheduleReviewed"]
        dashboard_time = status.get("reviewedAt")
        pipeline.host_and_approve_draft(
            drafts, queue, item_id, reviewer, note, checklist,
            os.environ.get("FUNZUG_MEDIA_BASE_URL", ""),
            os.environ.get("FUNZUG_MEDIA_UPLOAD_TOKEN", ""),
            "FUNZUG", "Yes, upload publicly and publish at scheduled time",
            dashboard_time,
        )
        queue = pipeline.load_json(pipeline.QUEUE_PATH)
        completed += 1
    print(f"BrandFlow approvals processed: {completed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("sync", "process-approvals"))
    args = parser.parse_args()
    try:
        return sync_pending() if args.command == "sync" else process_approvals()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
