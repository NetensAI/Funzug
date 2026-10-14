"""Owner-approved native Meta scheduling controller.

The browser adapter is responsible for reading the visible composer and planner.
Durable submission intent precedes the one Schedule click. On interruption the
only recovery operation is planner inspection, never another Schedule click.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import json
import re
from urllib.parse import urlsplit
from typing import Callable, Protocol

from PIL import Image

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class NativeFailure(RuntimeError):
    """Public diagnostic codes contain no image, caption or credential values."""


def stamp(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(IST)
    except (ValueError, TypeError, AttributeError):
        raise NativeFailure("invalid_schedule") from None


def verify_package(packet: dict) -> bytes:
    if packet.get('format', 'image') != 'image' or 'media' in packet:
        raise NativeFailure('unsupported_native_media_format')
    if packet.get("scheduleTimezone") != "Asia/Kolkata":
        raise NativeFailure("invalid_timezone")
    if not isinstance(packet.get("externalId"), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,199}',packet['externalId']):
        raise NativeFailure("invalid_item")
    stamp(packet.get("proposedSchedule"))
    platforms = packet.get("platforms")
    if not isinstance(platforms, list) or not platforms or len(set(platforms)) != len(platforms) or not set(platforms) <= {"facebook", "instagram"}:
        raise NativeFailure("invalid_platforms")
    image = packet.get("image", {})
    try:
        data = base64.b64decode(image["data"], validate=True)
        if not 0 < len(data) <= 12 * 1024 * 1024:
            raise ValueError()
        with Image.open(io.BytesIO(data)) as decoded:
            width, height = decoded.size
            expected_mime = {"PNG": "image/png", "JPEG": "image/jpeg"}.get(decoded.format)
            decoded.verify()
        if expected_mime != image["mimeType"] or (width, height) != (image["width"], image["height"]) or not 0 < width < height or abs(width * 5 - height * 4) > 2:
            raise ValueError()
    except (KeyError, ValueError, TypeError, OSError, Image.DecompressionBombError):
        raise NativeFailure("invalid_reviewed_image") from None
    content = {key: packet.get(key) for key in ("headline", "caption", "claims", "sources", "platforms")}
    if not isinstance(content["headline"], str) or not content["headline"].strip() or not isinstance(content["caption"], str) or not content["caption"].strip() or not isinstance(content["claims"], list) or not content["claims"] or not isinstance(content["sources"], list) or not content["sources"]:
        raise NativeFailure("invalid_reviewed_content")
    content.update(imageMimeType=image["mimeType"], imageSha256=hashlib.sha256(data).hexdigest())
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if digest != packet.get("contentHash"):
        raise NativeFailure("reviewed_content_changed")
    return data


def binding(packet: dict) -> dict:
    return {"item_id": packet["externalId"], "content_hash": packet["contentHash"], "scheduled_at": stamp(packet["proposedSchedule"]).isoformat(), "platforms": list(packet["platforms"])}


def verify_ordered_package(packet: dict) -> list[bytes]:
    """Independent mixed-package verification, not a delivery enable switch."""
    from scripts.reviewed_media import approval_fingerprint
    from scripts.validate_ordered_media import validate_ordered_media
    if packet.get('format') not in {'carousel', 'reel'} or 'image' in packet:
        raise NativeFailure('unsupported_native_media_format')
    if packet.get('scheduleTimezone') != 'Asia/Kolkata':
        raise NativeFailure('invalid_timezone')
    if not isinstance(packet.get('externalId'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,199}', packet['externalId']):
        raise NativeFailure('invalid_item')
    stamp(packet.get('proposedSchedule'))
    platforms = packet.get('platforms')
    if not isinstance(platforms, list) or not platforms or any(not isinstance(p, str) for p in platforms) or len(set(platforms)) != len(platforms) or not set(platforms) <= {'facebook', 'instagram'}:
        raise NativeFailure('invalid_platforms')
    for key in ('headline', 'caption'):
        if not isinstance(packet.get(key), str) or not packet[key].strip():
            raise NativeFailure('invalid_reviewed_content')
    if any(not isinstance(packet.get(key), list) or not packet[key] for key in ('claims', 'sources')):
        raise NativeFailure('invalid_reviewed_content')
    try:
        digest = approval_fingerprint(packet)
    except (ValueError, TypeError, KeyError):
        raise NativeFailure('invalid_reviewed_media') from None
    if digest != packet.get('contentHash'):
        raise NativeFailure('reviewed_content_changed')
    try:
        validate_ordered_media(packet)
        return [base64.b64decode(asset['data'], validate=True) for asset in packet['media']]
    except Exception:
        raise NativeFailure('invalid_reviewed_media') from None


class Browser(Protocol):
    def inspect(self, packet: dict) -> dict[str, dict]: ...
    def prepare(self, packet: dict, image: bytes | list[bytes]) -> dict: ...
    def prepared(self, packet: dict) -> dict: ...
    def submit(self) -> None: ...


def verify_proof(packet: dict, proof: dict, image: bytes | list[bytes]) -> None:
    expected = binding(packet)
    media_proof = ({'format': packet['format'], 'media_sha256': [hashlib.sha256(asset).hexdigest() for asset in image]}
                   if isinstance(image, list) else {'image_sha256': hashlib.sha256(image).hexdigest()})
    if proof != {**expected, "caption": packet["caption"], **media_proof, "timezone": "Asia/Kolkata", "story": False, "boost": False}:
        raise NativeFailure("composer_does_not_match_approval")


def verify_delivery_package(packet: dict, browser: Browser) -> bytes | list[bytes]:
    """Mixed adapters must explicitly advertise implemented format support.

    The deployed image adapter advertises none, preserving its fail-closed gate.
    Every refresh uses this same independent verification boundary.
    """
    media_format = packet.get('format', 'image')
    if media_format == 'image':
        return verify_package(packet)
    supported = getattr(browser, 'supported_media_formats', ())
    if not isinstance(supported, (tuple, frozenset)) or media_format not in supported:
        raise NativeFailure('unsupported_native_media_format')
    return verify_ordered_package(packet)


def verify_receipts(packet: dict, receipts: dict, now: dt.datetime) -> None:
    if not isinstance(receipts, dict) or not set(receipts) <= set(packet["platforms"]):
        raise NativeFailure("unexpected_planner_platform")
    for platform, receipt in receipts.items():
        if not isinstance(receipt, dict) or receipt.get("platform") != platform or not re.fullmatch(r"[0-9]+", str(receipt.get("schedule_id", ""))) or receipt.get("content_hash") != packet["contentHash"] or receipt.get("scheduled_at") != stamp(packet["proposedSchedule"]).isoformat() or stamp(receipt.get("checked_at")) > now:
            raise NativeFailure("planner_receipt_mismatch")
        url = receipt.get("planner_url", "")
        parsed = urlsplit(url) if isinstance(url, str) else None
        if parsed is None or parsed.scheme != "https" or parsed.hostname != "business.facebook.com" or parsed.username or parsed.password or parsed.port not in {None, 443} or not parsed.path.startswith("/latest/"):
            raise NativeFailure("planner_receipt_mismatch")
        handoff = packet.get("nativeHandoff")
        if handoff and handoff.get("submission_started_at") and stamp(receipt["checked_at"]) < stamp(handoff["submission_started_at"]):
            raise NativeFailure("stale_planner_receipt")


def advance(packet: dict, state: dict, browser: Browser, workflow: Callable, persist: Callable, refresh: Callable, now: dt.datetime) -> str:
    """Advance one item using an authenticated, freshly read approved package.

    workflow(action, item_id, receipt=None) waits for the persisted GitHub action
    and dashboard checkpoint. refresh() re-reads approval before public submission.
    persist(state) must atomically save state before it returns.
    """
    image = verify_delivery_package(packet, browser)
    expected = binding(packet)
    if state.get("binding") and state["binding"] != expected:
        raise NativeFailure("approval_changed_after_handoff")
    handoff = packet.get("nativeHandoff")
    if handoff:
        if handoff.get("content_hash") != expected["content_hash"] or handoff.get("scheduled_at") != expected["scheduled_at"] or handoff.get("platforms") != expected["platforms"]:
            raise NativeFailure("native_checkpoint_mismatch")
        if handoff.get("state") == "scheduled":
            observed = browser.inspect(packet)
            verify_receipts(packet, observed, dt.datetime.now(IST))
            saved = handoff.get("receipts", {})
            if set(observed) != set(packet["platforms"]) or any(saved.get(p, {}).get("schedule_id") != observed[p]["schedule_id"] for p in packet["platforms"]):
                raise NativeFailure("stored_schedule_not_visible_in_planner")
            return "scheduled"
    if not handoff:
        if state.get("phase"):
            if state.get('phase')=='reserve_intent' and 'reserve:'+packet['externalId']+':' in state.get('checkpoints',{}):
                workflow('reserve',packet['externalId'])
                state['phase']='reserved'
                persist(state)
                return 'reserved'
            raise NativeFailure("reservation_needs_reconciliation")
        if stamp(packet["proposedSchedule"]) <= now + dt.timedelta(minutes=10):
            raise NativeFailure("approved_slot_too_close")
        state.update(binding=expected, phase="reserve_intent")
        persist(state)
        workflow("reserve", packet["externalId"])
        state["phase"] = "reserved"
        persist(state)
        return "reserved"
    if handoff.get("state") == "reserved":
        if state.get('phase')=='begin_intent' and 'begin:'+packet['externalId']+':' in state.get('checkpoints',{}):
            # Observe the already-dispatched run. A successful workflow includes
            # both the authoritative queue commit and dashboard confirmation.
            workflow('begin',packet['externalId'])
            current=refresh()
            verify_delivery_package(current, browser)
            if binding(current)!=expected or current.get('nativeHandoff',{}).get('state')!='submitting':
                raise NativeFailure('submission_checkpoint_unconfirmed')
            return advance(current,state,browser,workflow,persist,refresh,dt.datetime.now(IST))
        if state.get("phase") not in {"reserved", "reserve_intent"}:
            raise NativeFailure("unowned_reservation_needs_reconciliation")
        if stamp(packet["proposedSchedule"]) <= now + dt.timedelta(minutes=10):
            raise NativeFailure("approved_slot_too_close")
        existing = browser.inspect(packet)
        if existing:
            # A pre-existing native post must be audited rather than submitted.
            raise NativeFailure("existing_planner_post_needs_reconciliation")
        verify_proof(packet, browser.prepare(packet, image), image)
        current = refresh()
        verify_delivery_package(current, browser)
        if binding(current) != expected or current.get("nativeHandoff") != handoff:
            raise NativeFailure("approval_changed_before_checkpoint")
        state["phase"] = "begin_intent"
        persist(state)
        workflow("begin", packet["externalId"])
        state["phase"] = "begin_confirmed"
        persist(state)
        current = refresh()
        verify_delivery_package(current, browser)
        if binding(current) != expected or current.get("nativeHandoff", {}).get("state") != "submitting":
            raise NativeFailure("submission_checkpoint_unconfirmed")
        if stamp(current["proposedSchedule"]) <= dt.datetime.now(IST):
            raise NativeFailure("approved_slot_expired_during_preparation")
        verify_proof(current, browser.prepared(current), image)
        state["phase"] = "submission_intent"
        persist(state)
        browser.submit()
        packet = current
    elif handoff.get('state')=='submitting' and state.get('phase') in {'begin_intent','begin_confirmed'}:
        key='begin:'+packet['externalId']+':'
        if key not in state.get('checkpoints',{}):
            raise NativeFailure('unowned_submission_checkpoint')
        workflow('begin',packet['externalId'])
        if state['checkpoints'][key].get('phase')!='success':
            raise NativeFailure('submission_checkpoint_unconfirmed')
        if stamp(packet['proposedSchedule'])<=dt.datetime.now(IST)+dt.timedelta(minutes=10):
            raise NativeFailure('approved_slot_too_close')
        if browser.inspect(packet):
            raise NativeFailure('existing_planner_post_needs_reconciliation')
        # A durable submission_intent is written before the public click. Only
        # phases preceding that marker may rebuild an unsent composer on restart.
        verify_proof(packet,browser.prepare(packet,image),image)
        current=refresh()
        verify_delivery_package(current, browser)
        if binding(current)!=expected or current.get('nativeHandoff')!=handoff:
            raise NativeFailure('approval_changed_before_submission')
        verify_proof(current,browser.prepared(current),image)
        state['phase']='submission_intent'
        persist(state)
        browser.submit()
        packet=current
    elif handoff.get("state") != "submitting":
        raise NativeFailure("unknown_native_checkpoint")
    # Both a returned click and an interrupted attempt are reconciled by reading
    # planner entries. No path from submission_intent calls submit a second time.
    observed = browser.inspect(packet)
    verify_receipts(packet, observed, dt.datetime.now(IST))
    if not observed:
        raise NativeFailure("native_submission_unconfirmed")
    saved = packet.get("nativeHandoff", {}).get("receipts", {})
    for platform in packet["platforms"]:
        if platform not in observed:
            continue
        if platform in saved:
            if saved[platform]["schedule_id"] != observed[platform]["schedule_id"]:
                raise NativeFailure("conflicting_planner_schedule")
            continue
        state["phase"] = "receipt_intent"
        state["receipt_platform"] = platform
        persist(state)
        workflow("receipt", packet["externalId"], observed[platform])
    if set(observed) != set(packet["platforms"]):
        raise NativeFailure("partial_native_submission")
    state["phase"] = "scheduled"
    state.pop("receipt_platform", None)
    persist(state)
    return "scheduled"
