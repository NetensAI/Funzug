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
    if not pipeline.workflow_delivery_allowed(item):
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--action", choices=("reserve", "begin", "receipt", "dashboard"), default="reserve")
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
        else:
            raw = os.environ.get("NATIVE_RECEIPT_JSON", "")
            if len(raw) > 4000:
                raise RuntimeError("receipt exceeds allowed size")
            receipt = json.loads(raw)
            if not isinstance(receipt, dict):
                raise RuntimeError("receipt must be an object")
            record_receipt(item, receipt, now)
        changed = True
    if changed:
        pipeline.save_json(pipeline.QUEUE_PATH, queue)
        event = {"event": "native_handoff_" + args.action, "item_id": args.id, "scheduled_at": item["scheduled_at"], "content_hash": reviewed["contentHash"], "state":item["native_handoff"]["state"]}
        if args.action == "receipt":
            event.update({"platform": receipt["platform"], "schedule_id": receipt["schedule_id"], "checked_at": receipt["checked_at"]})
        pipeline.log_event(event)
    print("Native handoff checkpoint persisted; browser planner verification remains required" if changed else "Native reservation already persisted; inspect planner before any submission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
