"""Reserve an existing owner approval before native Meta UI scheduling.

Reservation is deliberately fail-closed: it never schedules, posts or releases a
reservation. An interrupted browser submission needs planner reconciliation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import funzug_pipeline as pipeline
from scripts import brandflow_sync as sync


def reserve(item: dict[str, Any], reviewed: dict[str, Any], now: dt.datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("reservation clock must be timezone aware")
    if item.get("status") != "approved" or reviewed.get("status") != "approved":
        raise RuntimeError("native handoff requires an existing owner approval")
    if reviewed.get("publicationAuthorized") is not True or reviewed.get("scheduleTimezone") != "Asia/Kolkata":
        raise RuntimeError("native handoff requires explicit authorization and IST")
    approval = item.get("approval", {})
    if approval.get("status") != "approved" or not pipeline.valid_review_checklist(approval.get("review_checklist")):
        raise RuntimeError("native handoff requires the persisted approval confirmation")
    if item.get("format") != "image" or not item.get("platforms") or not set(item["platforms"]) <= {"facebook", "instagram"}:
        raise RuntimeError("native handoff currently supports reviewed single images only")
    if item.get("platform_results"):
        raise RuntimeError("recorded platform outcomes require platform-specific reconciliation")
    slot = pipeline.parse_schedule_time(item["scheduled_at"])
    if slot <= now:
        raise RuntimeError("native schedule must remain in the future")
    if slot != pipeline.parse_time(reviewed.get("proposedSchedule")):
        raise RuntimeError("native handoff cannot change the owner-approved slot")
    sync.require_matching_approved_content(item, reviewed)
    existing = item.get("native_handoff")
    if "native_handoff" in item:
        if isinstance(existing, dict) and existing.get("state") == "reserved" and existing.get("content_hash") == reviewed.get("contentHash") and existing.get("scheduled_at") == slot.isoformat():
            return False
        raise RuntimeError("existing native handoff requires planner reconciliation")
    if not pipeline.workflow_delivery_allowed(item) and item.get('delivery_mode')!='meta_native_pending':
        raise RuntimeError("unknown delivery mode requires reconciliation")
    item["delivery_mode"] = "meta_native"
    item["native_handoff"] = {
        "state": "reserved",
        "reserved_at": now.isoformat(),
        "scheduled_at": slot.isoformat(),
        "content_hash": reviewed["contentHash"],
        "platforms": list(item["platforms"]),
        "receipts": {},
    }
    return True


def begin_submission(item: dict[str, Any], now: dt.datetime) -> None:
    handoff = item.get("native_handoff")
    if not isinstance(handoff, dict) or handoff.get("state") != "reserved":
        raise RuntimeError("only an unsubmitted reservation may begin native scheduling")
    if pipeline.parse_schedule_time(item["scheduled_at"]) <= now:
        raise RuntimeError("native slot has passed; reconcile instead of submitting")
    if item["scheduled_at"] != handoff.get("scheduled_at") or item.get("platform_results"):
        raise RuntimeError("reserved schedule or publication state changed")
    handoff["state"] = "submitting"
    handoff["submission_started_at"] = now.isoformat()


def record_receipt(item: dict[str, Any], receipt: dict[str, Any], now: dt.datetime) -> None:
    handoff = item.get("native_handoff")
    if not isinstance(handoff, dict) or handoff.get("state") not in {"submitting", "scheduled"}:
        raise RuntimeError("native receipt requires a persisted submission checkpoint")
    platform = receipt.get("platform")
    if platform not in handoff.get("platforms", []):
        raise RuntimeError("receipt platform is not owner-approved")
    if receipt.get("scheduled_at") != handoff.get("scheduled_at") or receipt.get("content_hash") != handoff.get("content_hash"):
        raise RuntimeError("receipt does not match the reserved content and IST slot")
    schedule_id = receipt.get("schedule_id")
    if (
        not isinstance(schedule_id, str)
        or not schedule_id.strip()
        or len(schedule_id) > 200
        or schedule_id.strip().casefold().startswith("meta-planner-visible:")
    ):
        raise RuntimeError("receipt requires the observed Meta schedule identifier")
    url = urllib.parse.urlsplit(receipt.get("planner_url", ""))
    if url.scheme != "https" or url.hostname != "business.facebook.com" or url.username or url.password:
        raise RuntimeError("receipt must reference the observed Meta Business Suite page")
    checked_at = pipeline.parse_time(receipt.get("checked_at"))
    started_at = pipeline.parse_time(handoff["submission_started_at"])
    if checked_at < started_at or checked_at > now:
        raise RuntimeError("receipt observation must follow submission and not be in the future")
    saved = {key:receipt[key] for key in ("platform", "schedule_id", "scheduled_at", "content_hash", "planner_url", "checked_at")}
    previous = handoff["receipts"].get(platform)
    if previous is not None and previous != saved:
        previous_id = previous.get("schedule_id") if isinstance(previous, dict) else None
        if not isinstance(previous_id, str) or not previous_id.strip().casefold().startswith("meta-planner-visible:"):
            raise RuntimeError("conflicting receipt requires native schedule reconciliation")
    handoff["receipts"][platform] = saved
    all_platforms_confirmed = all(
        isinstance(handoff["receipts"].get(required_platform), dict)
        and isinstance(handoff["receipts"][required_platform].get("schedule_id"), str)
        and not handoff["receipts"][required_platform]["schedule_id"].strip().casefold().startswith("meta-planner-visible:")
        for required_platform in handoff["platforms"]
    )
    if all_platforms_confirmed:
        handoff["state"] = "scheduled"
    else:
        handoff["state"] = "submitting"
    # Keep delivery_mode blocked even after confirmation. Meta now owns delivery.


def record_published_outcomes(item: dict[str, Any], raw: dict[str, Any], now: dt.datetime) -> bool:
    """Record already-published native Meta outcomes after direct UI verification."""
    handoff = item.get("native_handoff")
    was_published = item.get("status") == "published"
    if item.get("status") not in {"approved", "published"} or not isinstance(handoff, dict) or handoff.get("state") != "scheduled":
        raise RuntimeError("publication reconciliation requires an approved, natively scheduled post")
    if item.get("platform_results") and not was_published:
        raise RuntimeError("existing platform outcomes require explicit conflict reconciliation")
    results = raw.get("platform_results")
    platforms = item.get("platforms", [])
    if not isinstance(results, dict) or set(results) != set(platforms):
        raise RuntimeError("outcomes must cover exactly the owner-approved platforms")

    slot = pipeline.parse_schedule_time(item["scheduled_at"])
    saved: dict[str, dict[str, str]] = {}
    for platform in platforms:
        result = results.get(platform)
        if not isinstance(result, dict) or set(result) != {"post_id", "published_at", "evidence_url"}:
            raise RuntimeError("each publication outcome requires a Meta post ID, time, and evidence URL")
        post_id = result.get("post_id")
        if not isinstance(post_id, str) or not post_id.strip() or len(post_id) > 200:
            raise RuntimeError("Meta post ID is invalid")
        receipt = handoff.get("receipts", {}).get(platform)
        if not isinstance(receipt, dict) or receipt.get("schedule_id") != post_id:
            raise RuntimeError("published post ID does not match the observed native Meta receipt")
        published_at = pipeline.parse_time(result.get("published_at"))
        if published_at > now or abs(published_at - slot) > dt.timedelta(minutes=15):
            raise RuntimeError("publication time is not consistent with the approved IST slot")
        url = urllib.parse.urlsplit(result.get("evidence_url", ""))
        query = urllib.parse.parse_qs(url.query)
        if (
            url.scheme != "https"
            or url.hostname != "business.facebook.com"
            or url.username
            or url.password
            or url.path.rstrip("/") != "/latest/insights/object_insights"
            or query.get("content_id") != [post_id]
        ):
            raise RuntimeError("publication evidence must be the matching Meta Business Suite post detail")
        saved[platform] = {
            "status": "published",
            "published_at": published_at.isoformat(),
            "post_id": post_id,
        }

    if was_published:
        if item.get("platform_results") == saved:
            return False
        raise RuntimeError("published outcome conflicts with the existing record")

    item["platform_results"] = saved
    item["status"] = "published"
    item["last_attempt_at"] = now.isoformat()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--action", choices=("reserve", "begin", "receipt", "published", "dashboard"), default="reserve")
    args = parser.parse_args()
    queue = pipeline.load_json(pipeline.QUEUE_PATH)
    errors = pipeline.validate_queue(queue)
    if errors:
        raise RuntimeError("queue validation failed: " + "; ".join(errors))
    item = next((row for row in queue.get("items", []) if row.get("id") == args.id), None)
    if item is None:
        raise RuntimeError("approved item is absent")
    reviewed = sync.api_status(sync.api_url(), sync.secret()).get(args.id, {})
    now = dt.datetime.now(sync.SCHEDULE_TIMEZONE)
    if args.action == "dashboard":
        sync.require_matching_approved_content(item, reviewed)
        handoff = item.get("native_handoff")
        if not isinstance(handoff, dict):
            raise RuntimeError("persisted native handoff is missing")
        endpoint = sync.api_url().rsplit("/", 1)[0] + "/native-handoff"
        result = sync.api_request("POST", endpoint, sync.secret(), {"batchId":sync.BATCH_ID,"externalId":args.id,"handoff":handoff})
        if result.get("externalId") != args.id or result.get("state") != handoff.get("state"):
            raise RuntimeError("dashboard did not confirm native handoff checkpoint")
        print("BrandFlow native checkpoint confirmed; planner verification remains required")
        return 0
    if args.action == "reserve":
        changed = reserve(item, reviewed, now)
    else:
        sync.require_matching_approved_content(item, reviewed)
        if reviewed.get("status") != "approved" or reviewed.get("publicationAuthorized") is not True or pipeline.parse_time(reviewed.get("proposedSchedule")) != pipeline.parse_schedule_time(item["scheduled_at"]):
            raise RuntimeError("current owner approval no longer matches native reservation")
        if args.action == "begin":
            begin_submission(item, now)
        elif args.action == "receipt":
            raw = os.environ.get("NATIVE_RECEIPT_JSON", "")
            if len(raw) > 4000:
                raise RuntimeError("receipt exceeds allowed size")
            receipt = json.loads(raw)
            if not isinstance(receipt, dict):
                raise RuntimeError("receipt must be an object")
            record_receipt(item, receipt, now)
        else:
            raw = os.environ.get("NATIVE_OUTCOME_JSON", "")
            if len(raw) > 4000:
                raise RuntimeError("publication outcome exceeds allowed size")
            outcome = json.loads(raw)
            if not isinstance(outcome, dict):
                raise RuntimeError("publication outcome must be an object")
            changed = record_published_outcomes(item, outcome, now)
        if args.action in {"begin", "receipt"}:
            changed = True
    if changed:
        pipeline.save_json(pipeline.QUEUE_PATH, queue)
        event = {"event": "native_handoff_" + args.action, "item_id": args.id, "scheduled_at": item["scheduled_at"], "content_hash": reviewed["contentHash"], "state":item["native_handoff"]["state"]}
        if args.action == "receipt":
            event.update({"platform": receipt["platform"], "schedule_id": receipt["schedule_id"], "checked_at": receipt["checked_at"]})
        elif args.action == "published":
            event["platforms"] = sorted(item["platform_results"])
            event["source"] = "Meta Business Suite"
            history = pipeline.load_json(pipeline.HISTORY_PATH) if pipeline.HISTORY_PATH.exists() else {"checked_at": None, "source": "Funzug publishing workflow", "topic_keys": []}
            topics = history.get("topic_keys", [])
            known_topics = {topic for topic in topics if isinstance(topic, str)} if isinstance(topics, list) else set()
            if item.get("topic_key"):
                known_topics.add(item["topic_key"])
            history["checked_at"] = now.isoformat()
            history["topic_keys"] = sorted(known_topics)
            pipeline.save_json(pipeline.HISTORY_PATH, history)
            for platform, result in item["platform_results"].items():
                pipeline.log_event({"event":"published", "item_id":args.id, "platform":platform, "post_id":result["post_id"], "published_at":result["published_at"], "source":"Meta Business Suite"})
        pipeline.log_event(event)
    if args.action == "published":
        print("Verified native Meta publication outcome persisted; BrandFlow sync is required")
    else:
        print("Native handoff checkpoint persisted; browser planner verification remains required" if changed else "Native reservation already persisted; inspect planner before any submission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
