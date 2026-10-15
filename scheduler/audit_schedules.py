"""Read existing native image schedules without approving or submitting posts."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import time

from scheduler.native_runner import BATCH, candidates, read_api, safe_error_diagnostics
from scheduler.native_worker import IST, NativeFailure, verify_package, verify_receipts


def audit_packet(packet, browser, now):
    verify_package(packet)
    handoff = packet.get('nativeHandoff') or {}
    if handoff.get('state') != 'scheduled':
        raise NativeFailure('audit_requires_existing_schedule')
    observed = browser.inspect(packet)
    verify_receipts(packet, observed, now())
    saved = handoff.get('receipts', {})
    if set(observed) != set(packet['platforms']) or any(
        saved.get(platform, {}).get('schedule_id') != receipt['schedule_id']
        for platform, receipt in observed.items()
    ):
        raise NativeFailure('stored_schedule_not_visible_in_planner')
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='/run/secrets/config.json')
    parser.add_argument('--state', default='/state/native-worker.json')
    args = parser.parse_args()
    import fcntl
    from playwright.sync_api import sync_playwright
    from scheduler.meta_browser import MetaBrowser

    # Share the worker lock. This command must never overlap a submission.
    with Path(args.state).with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = Path(args.state)
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state.get('browser_retry_after', 0) > time.time():
            raise NativeFailure('native_browser_cooldown_active')
        config = json.loads(Path(args.config).read_text())
        rows = read_api(config, 'drafts', {'batchId': BATCH}).get('drafts')
        if not isinstance(rows, list):
            raise NativeFailure('draft_status_unavailable')
        now = lambda: dt.datetime.now(IST)
        selected = [row for row in candidates(rows, now())
                    if (row.get('nativeHandoff') or {}).get('state') == 'scheduled'
                    and row.get('media_format', row.get('format', 'image')) == 'image']
        failures = 0
        with sync_playwright() as playwright:
            connection = playwright.chromium.connect_over_cdp('http://127.0.0.1:9222')
            if len(connection.contexts) != 1:
                raise NativeFailure('persistent_browser_context_unavailable')
            for row in selected:
                identifier = row.get('externalId')
                if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,199}', identifier):
                    raise NativeFailure('invalid_item')
                adapter = None
                try:
                    packet = read_api(config, 'native-package', {'batchId': BATCH, 'externalId': identifier})
                    adapter = MetaBrowser(connection.contexts[0], Path('/tmp/funzug-audit') / identifier)
                    receipts = audit_packet(packet, adapter, now)
                    result = {'item_id': identifier, 'status': 'verified', 'receipts': receipts}
                except Exception as error:
                    failures += 1
                    result = {'item_id': identifier, 'status': 'failed',
                              'error': str(error) if isinstance(error, NativeFailure) else 'planner_audit_failed'}
                    if not isinstance(error, NativeFailure):
                        result.update(safe_error_diagnostics(error))
                finally:
                    if adapter:
                        adapter.close()
                print(json.dumps(result), flush=True)
        print(json.dumps({'checked': len(selected), 'failed': failures}), flush=True)
        return int(failures > 0)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except NativeFailure as error:
        print(json.dumps({'status':'failed','error':str(error)}), flush=True)
        raise SystemExit(1)
    except BlockingIOError:
        print(json.dumps({'status':'failed','error':'native_worker_owns_browser_lock'}), flush=True)
        raise SystemExit(1)
