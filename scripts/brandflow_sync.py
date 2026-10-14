#!/usr/bin/env python3
"""Sync review-only Funzug drafts with BrandFlow and consume explicit approvals."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import hashlib
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
from scripts.reviewed_media import approval_fingerprint
from scripts.validate_ordered_media import validate_ordered_media, probe_video_asset


DEFAULT_API = "https://funzug.netens.top/api/integrations/funzug/drafts"
BATCH_ID = "funzug-draft-inbox-v1"
SCHEDULE_TIMEZONE = ZoneInfo("Asia/Kolkata")

def api_request(method: str, url: str, secret: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Authorization", "Bearer " + secret)
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "FunzugWorkflow/1.0")
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
    value = os.environ.get("FUNZUG_DRAFT_INGEST_SECRET", "").strip()
    if len(value) < 32:
        raise RuntimeError("FUNZUG_DRAFT_INGEST_SECRET is not configured")
    if not value.isascii() or any(not 33 <= ord(char) <= 126 for char in value):
        raise RuntimeError("FUNZUG_DRAFT_INGEST_SECRET contains invalid characters")
    return value


def api_status(base_url: str, token: str) -> dict[str, dict[str, Any]]:
    url = base_url + "?" + urllib.parse.urlencode({"batchId": BATCH_ID})
    data = api_request("GET", url, token)
    rows = data.get("drafts")
    if not isinstance(rows, list):
        raise RuntimeError("BrandFlow status response is invalid")
    return {row["externalId"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("externalId"), str)}


def payload_for(item: dict[str, Any]) -> dict[str, Any]:
    if item.get('format') in {'carousel', 'reel'}:
        return ordered_payload_for(item)
    relpath = item.get("media_path")
    if not isinstance(relpath, str) or item.get("format") != "image":
        raise ValueError(f"{item.get('id', '<unknown>')}: only single-image drafts are supported by this integration")
    path = (ROOT / relpath).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError:
        raise ValueError("draft image path must stay inside the repository") from None
    if not path.is_file():
        raise ValueError(f"{item.get('id', '<unknown>')}: image is missing")
    dimensions = pipeline.image_size(path)
    if not pipeline.is_portrait_4_5(dimensions):
        raise ValueError(f"{item.get('id', '<unknown>')}: image must be portrait 4:5")
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
                "width": dimensions[0],
                "height": dimensions[1],
                "data": base64.b64encode(path.read_bytes()).decode("ascii"),
            },
        }],
    }


def ordered_payload_for(item: dict[str, Any]) -> dict[str, Any]:
    kind = item.get('format')
    paths = item.get('media_paths') if kind == 'carousel' else [item.get('media_path')]
    if not isinstance(paths, list) or not (2 <= len(paths) <= 10 if kind == 'carousel' else len(paths) == 1):
        raise ValueError('Carousel requires 2 to 10 private media paths')
    media = []
    for relative in paths:
        if not isinstance(relative, str) or not relative:
            raise ValueError('Invalid private media path')
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError:
            raise ValueError('Draft media path must stay inside the repository') from None
        if not path.is_file() or path.stat().st_size > (12 if kind == 'carousel' else 100) * 1024 * 1024:
            raise ValueError('Draft media is missing or exceeds the size limit')
        if kind == 'reel':
            media.append(probe_video_asset(path))
            continue
        dimensions = pipeline.image_size(path)
        mime = mimetypes.guess_type(path.name)[0]
        if not pipeline.is_portrait_4_5(dimensions) or mime not in {'image/png', 'image/jpeg'}:
            raise ValueError('Carousel slides must be portrait 4:5 PNG or JPEG')
        media.append(dict(mimeType=mime, width=dimensions[0], height=dimensions[1], data=base64.b64encode(path.read_bytes()).decode('ascii')))
    draft = {
        'externalId': item['id'], 'format': kind, 'media': media,
        'headline': item['headline'], 'caption': item['caption'],
        'claims': [{key: claim[key] for key in ('text', 'source_ids', 'support_note')} for claim in item['claims']],
        'sources': [{key: source[key] for key in ('id', 'title', 'publisher', 'url', 'published_at', 'checked_at')} for source in item['sources']],
        'platforms': item['platforms'],
        'proposedSchedule': pipeline.parse_time(item['scheduled_at']).astimezone(SCHEDULE_TIMEZONE).isoformat(),
        'scheduleTimezone': 'Asia/Kolkata',
    }
    validate_ordered_media(draft)
    packet = dict(schemaVersion=2, brandSlug='funzug', batchId=BATCH_ID, drafts=[draft])
    if len(json.dumps(packet, separators=(',', ':')).encode()) > 13 * 1024 * 1024:
        raise ValueError('Ordered draft JSON exceeds the 13 MB ingestion limit')
    return packet


def approval_content_hash(item: dict[str, Any]) -> str:
    draft = payload_for(item)["drafts"][0]
    return approval_fingerprint(draft)


def require_matching_approved_content(item: dict[str, Any], status: dict[str, Any]) -> None:
    expected = status.get("contentHash")
    if not isinstance(expected, str) or len(expected) != 64 or expected != approval_content_hash(item):
        raise RuntimeError(f"{item['id']}: repository content does not match BrandFlow reviewed content; sync pending revisions before owner approval")


def acceptance_inbox():
    inbox = pipeline.load_json(ROOT / 'drafts/tests/queue.json')
    expected = {'funzug-test-2026-10-16-carousel','funzug-test-2026-10-16-reel'}
    items = inbox.get('items', [])
    if len(items) != 2 or {item.get('id') for item in items} != expected or any(item.get('status') != 'draft' for item in items):
        raise RuntimeError('Acceptance inbox must contain exactly the two authorized unapproved tests')
    slots = {'carousel':'2026-10-16T20:00:00+05:30','reel':'2026-10-16T20:15:00+05:30'}
    if any(item.get('scheduled_at') != slots.get(item.get('format')) or item.get('platforms') != ['facebook','instagram'] for item in items):
        raise RuntimeError('Acceptance test platforms or owner-authorized IST slots changed')
    return inbox


def sync_pending(update_pending: bool = False, acceptance_tests: bool = False) -> int:
    token, base = secret(), api_url()
    inbox = acceptance_inbox() if acceptance_tests else pipeline.load_json(pipeline.DRAFT_QUEUE_PATH)
    errors = pipeline.validate_draft_queue(inbox)
    if errors:
        raise RuntimeError("draft validation failed:\n" + "\n".join(errors))
    known = api_status(base, token)
    sent = 0
    for item in inbox["items"]:
        item_id = item["id"]
        row = known.get(item_id)
        if row is not None and not (
            update_pending and row.get("status") == "pending_review"
            and row.get("publicationAuthorized") is False
            and not row.get("publishedAt")
        ):
            continue
        api_request("POST", base, token, payload_for(item))
        sent += 1
    print(f"BrandFlow sync complete: {sent} draft(s) transferred")
    return 0


def sync_results() -> int:
    token, base = secret(), api_url()
    endpoint = base
    drafts = pipeline.load_json(pipeline.DRAFT_QUEUE_PATH)
    original = {item["id"]: item for item in drafts.get("items", [])}
    queue = pipeline.load_json(pipeline.QUEUE_PATH)
    sent = 0
    for item in queue.get("items", []):
        if item.get("status") not in {"published", "failed"} or item.get("id") not in original:
            continue
        # Retry records can target one platform even when the approved draft
        # authorized both. The draft is the original platform authority.
        expected = set(original[item["id"]].get("platforms", []))
        results = item.get("platform_results", {})
        if not expected or not results or not set(results).issubset(expected):
            raise RuntimeError(f"{item['id']}: platform results do not match the approved draft")
        if item.get("status") == "published" and set(results) != expected:
            raise RuntimeError(f"{item['id']}: published platform results are incomplete")
        summary = {}
        for platform in sorted(results):
            result = results[platform]
            if result.get("status") == "failed":
                if item.get("status") == "published":
                    raise RuntimeError(f"{item['id']}: published item contains a failed platform")
                pipeline.parse_time(result.get("failed_at"))
                summary[platform] = {"status": "failed", "failedAt": result["failed_at"]}
                continue
            if result.get("status") != "published" or not result.get("post_id") or not result.get("published_at"):
                raise RuntimeError(f"{item['id']}: published platform result is invalid")
            summary[platform] = {
                "status": "published",
                "postId": result["post_id"],
                "publishedAt": result["published_at"],
            }
        api_request("PUT", endpoint, token, {
            "batchId": BATCH_ID,
            "externalId": item["id"],
            "platformResults": summary,
        })
        sent += 1
    print(f"BrandFlow publication results synced: {sent}")
    return 0


def reschedule_approved_item(queue: dict[str, Any], item_id: str, scheduled_at: str, changed_by: str, note: str, changed_at: str) -> tuple[str, str]:
    new_time = pipeline.parse_time(scheduled_at).astimezone(dt.timezone.utc)
    if new_time <= dt.datetime.now(dt.timezone.utc):
        raise RuntimeError("rescheduled time must be in the future")
    change_time = pipeline.parse_time(changed_at)
    if not changed_by.strip() or not note.strip():
        raise RuntimeError("reschedule requires a reviewer name and note")
    for item in queue.get("items", []):
        if item.get("id") != item_id:
            continue
        approval = item.get("approval")
        if item.get("status") != "approved" or not isinstance(approval, dict) or approval.get("status") != "approved":
            raise RuntimeError(f"{item_id}: only an approved, unpublished post can be rescheduled")
        if not pipeline.workflow_delivery_allowed(item):
            raise RuntimeError(f"{item_id}: native Meta handoff requires schedule reconciliation")
        if item.get("platform_results"):
            raise RuntimeError(f"{item_id}: recorded platform results require platform-specific recovery")
        previous = pipeline.parse_time(item["scheduled_at"])
        if previous.astimezone(dt.timezone.utc) == new_time:
            return previous.isoformat(), previous.isoformat()
        updated = new_time.astimezone(SCHEDULE_TIMEZONE).isoformat(timespec="seconds")
        item["scheduled_at"] = updated
        approval.setdefault("schedule_changes", []).append({
            "previous_schedule": previous.isoformat(),
            "scheduled_at": updated,
            "changed_by": changed_by.strip(),
            "changed_at": change_time.isoformat(),
            "note": note.strip(),
        })
        return previous.isoformat(), updated
    raise RuntimeError(f"{item_id}: approved post is absent from the publishing queue")


def approve_native_draft(drafts, queue, item_id, reviewer, note, approved_at, content_hash):
    """Stage privately decoded media only after matching explicit dashboard review."""
    candidate = next((item for item in drafts.get('items', []) if item.get('id') == item_id), None)
    if not candidate or candidate.get('status') != 'draft':
        raise RuntimeError('Native approval requires an existing unapproved draft')
    if any(item.get('id') == item_id for item in queue.get('items', [])):
        raise RuntimeError('Native item is already in the publish queue')
    if approval_content_hash(candidate) != content_hash:
        raise RuntimeError('Reviewed native media changed')
    errors = pipeline.validate_draft_queue(drafts)
    if errors:
        raise RuntimeError('Native draft validation failed: ' + '\n'.join(errors))
    item = json.loads(json.dumps(candidate))
    item['delivery_mode'] = 'meta_native_pending'
    item['reviewed_content_hash'] = content_hash
    staged = {**queue, 'items':[*queue.get('items', []), item]}
    pipeline.approve(staged, item_id, reviewer, note, {'approvalConfirmed':True}, approved_at)


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
        if status.get("scheduleTimezone") != "Asia/Kolkata":
            raise RuntimeError(f"{item_id}: approved schedule must use Asia/Kolkata")
        reviewer = status.get("reviewedBy")
        note = status.get("reviewNote")
        if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(note, str) or not note.strip():
            raise RuntimeError(f"{item_id}: approval is missing reviewer identity or note")
        selected_schedule = status.get("proposedSchedule")
        if not isinstance(selected_schedule, str):
            raise RuntimeError(f"{item_id}: approved schedule is missing")
        local_schedule = pipeline.parse_time(selected_schedule).astimezone(SCHEDULE_TIMEZONE)
        dashboard_time = status.get("reviewedAt")
        existing = next((item for item in queue.get("items", []) if item.get("id") == item_id), None)
        # BrandFlow can lag behind publishing. Completed posts must not block
        # later approvals or be rescheduled from a stale dashboard status.
        if existing is not None and existing.get("status") == "published":
            continue
        if existing is not None:
            if existing.get("status") != "approved":
                raise RuntimeError(f"{item_id}: only an approved, unpublished post can be rescheduled")
            if pipeline.parse_time(existing["scheduled_at"]).astimezone(dt.timezone.utc) == local_schedule.astimezone(dt.timezone.utc):
                continue
            approval = existing.get("approval", {})
            approved_at = approval.get("approved_at") if isinstance(approval, dict) else None
            if not isinstance(dashboard_time, str) or not isinstance(approved_at, str):
                raise RuntimeError(f"{item_id}: reschedule requires the original approval and a new review timestamp")
            if pipeline.parse_time(dashboard_time).astimezone(dt.timezone.utc) <= pipeline.parse_time(approved_at).astimezone(dt.timezone.utc):
                raise RuntimeError(f"{item_id}: schedule change has no new BrandFlow review timestamp")
            previous, updated = reschedule_approved_item(
                queue, item_id, local_schedule.isoformat(), reviewer, note, dashboard_time,
            )
            pipeline.save_json(pipeline.QUEUE_PATH, queue)
            pipeline.log_event({
                "event": "schedule_rescheduled",
                "item_id": item_id,
                "changed_by": reviewer,
                "previous_schedule": previous,
                "scheduled_at": updated,
            })
            completed += 1
            continue
        item = local.get(item_id)
        if not item or item.get("status") != "draft":
            raise RuntimeError(f"{item_id}: approved post is absent from the local draft inbox")
        if local_schedule <= dt.datetime.now(SCHEDULE_TIMEZONE):
            print(f"{item_id}: skipped expired BrandFlow approval; no media upload or queue change")
            continue
        require_matching_approved_content(item, status)
        item["scheduled_at"] = local_schedule.isoformat()
        delivery_mode=os.environ.get('FUNZUG_DELIVERY_MODE','workflow') or 'workflow'
        if delivery_mode not in {'workflow','meta_native'}:
            raise RuntimeError('Configured Funzug delivery mode is invalid')
        if delivery_mode=='meta_native':
            # stage_draft copies this marker before recording approval. The
            # due-time API publisher must not race the native browser worker.
            item['delivery_mode']='meta_native_pending'
            approve_native_draft(drafts, queue, item_id, reviewer, note, dashboard_time, status['contentHash'])
            queue = pipeline.load_json(pipeline.QUEUE_PATH)
            completed += 1
            continue
        checklist = {"approvalConfirmed": True}
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
    parser.add_argument("command", choices=("sync", "process-approvals", "sync-results"))
    parser.add_argument("--update-pending", action="store_true", help="Update unreviewed existing drafts only; never approved or published content")
    parser.add_argument('--acceptance-tests', action='store_true', help='Sync only the two owner-authorized mixed delivery test drafts')
    args = parser.parse_args()
    if args.update_pending and args.command != "sync":
        parser.error("--update-pending is valid only with sync")
    if args.acceptance_tests and (args.command != 'sync' or args.update_pending):
        parser.error('--acceptance-tests is valid only for sync without --update-pending')
    try:
        if args.command == "sync":
            return sync_pending(update_pending=args.update_pending, acceptance_tests=args.acceptance_tests)
        if args.command == "sync-results":
            return sync_results()
        return process_approvals()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
