"""Dedicated native Meta worker. Disabled until explicit deployment cutover."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import signal
from pathlib import Path
import time
import traceback
from urllib.parse import urlencode, urlsplit
from urllib.request import Request

from instagram_credentials import request_json
from scheduler.native_dispatch import CheckpointDispatcher
from scheduler.native_worker import IST, NativeFailure, advance, stamp, verify_delivery_package
from scheduler.runner import write_state
from scripts.renew_instagram_credential import installation_token
from scripts.mixed_delivery_policy import ACCEPTANCE_IDS, CANCELLED_IDS, mixed_delivery_enabled

BATCH = 'funzug-draft-inbox-v1'
DEFAULT_API = 'https://funzug.netens.top/api/integrations/funzug'
SCHEDULE_REVERIFY_SECONDS = 6 * 60 * 60
BROWSER_COOLDOWN_SECONDS = 60 * 60


def defer_browser(state, reason, now):
    if reason not in {'meta_temporarily_blocked', 'meta_planner_unavailable'}:
        raise NativeFailure('invalid_browser_deferral')
    state['browser_block_reason'] = reason
    state['browser_retry_after'] = int(now) + BROWSER_COOLDOWN_SECONDS
    state['browser_blocked_at'] = int(now)


def recently_verified(row, local, now):
    expected = local.get('binding', {})
    return (not local.get('error') and local.get('status') == 'scheduled'
            and expected.get('content_hash') == row.get('contentHash')
            and expected.get('scheduled_at') == stamp(row.get('proposedSchedule')).isoformat()
            and local.get('last_verified_at', 0) > now - SCHEDULE_REVERIFY_SECONDS)


def read_api(config, route, query):
    base = config.get('native_api_url', DEFAULT_API)
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or parsed.hostname != 'funzug.netens.top' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise NativeFailure('invalid_native_api_origin')
    return request_json(Request(base.rstrip('/') + '/' + route + '?' + urlencode(query), headers={'Authorization':'Bearer ' + config['draft_secret'],'Accept':'application/json','User-Agent':'FunzugWorkflow/1.0'}))


def auth(config):
    os.environ['FUNZUG_GH_APP_ID'] = '5281589'
    os.environ['FUNZUG_GH_APP_PRIVATE_KEY'] = Path(config['key_file']).read_text()
    try:
        return installation_token({'actions':'write'})
    finally:
        os.environ.pop('FUNZUG_GH_APP_PRIVATE_KEY', None)


def delivery_allowed(row):
    identifier = row.get('externalId')
    if isinstance(identifier, str) and identifier in CANCELLED_IDS:
        return False
    media_format = row.get('media_format', row.get('format', 'image'))
    expected_format = {
        'funzug-test-2026-10-22-carousel': 'carousel',
        'funzug-test-2026-10-22-reel': 'reel',
    }.get(identifier) if isinstance(identifier, str) else None
    if isinstance(identifier, str) and identifier in ACCEPTANCE_IDS and media_format != expected_format:
        return False
    return media_format not in {'carousel', 'reel'} or mixed_delivery_enabled(identifier, os.environ)


def candidates(rows, now):
    result=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('status')!='approved' or row.get('publicationAuthorized') is not True or row.get('publishedAt'):
            continue
        if not delivery_allowed(row):
            continue
        if row.get('scheduleTimezone')!='Asia/Kolkata':
            raise NativeFailure('invalid_timezone')
        if stamp(row.get('proposedSchedule'))<=now:
            continue
        result.append(row)
    return sorted(result,key=lambda row:stamp(row['proposedSchedule']))


def publication_candidates(rows,now):
    """Read-only reconciliation of due native schedules, never a retry publish."""
    result=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('status')!='approved' or row.get('publicationAuthorized') is not True or row.get('publishedAt'):
            continue
        if not delivery_allowed(row):
            continue
        if (row.get('nativeHandoff') or {}).get('state')!='scheduled':
            continue
        if row.get('scheduleTimezone')!='Asia/Kolkata':
            raise NativeFailure('invalid_timezone')
        if stamp(row.get('proposedSchedule'))<=now-dt.timedelta(minutes=2):
            result.append(row)
    return sorted(result,key=lambda row:stamp(row['proposedSchedule']))


def reconcile_recorded_publications(rows,state,now=None):
    """Clear stale local checkpoints when BrandFlow already records completion."""
    items=state.get('items')
    if not isinstance(items,dict):
        return 0
    reconciled=0
    checked_at=int(time.time() if now is None else now)
    for row in rows:
        if not isinstance(row,dict):
            continue
        identifier=row.get('externalId')
        published_at=row.get('publishedAt')
        local=items.get(identifier) if isinstance(identifier,str) else None
        if not isinstance(published_at,str) or not published_at or not isinstance(local,dict):
            continue
        if (local.get('status')=='published' and local.get('published_at')==published_at
                and not local.get('error') and not local.get('error_diagnostics')):
            continue
        local['status']='published'
        local['published_at']=published_at
        local['reconciled_at']=checked_at
        local.pop('error',None)
        local.pop('error_diagnostics',None)
        reconciled+=1
    return reconciled


def safe_error_diagnostics(error):
    allowed = {'Error', 'TimeoutError', 'AttributeError', 'TypeError',
               'ValueError', 'KeyError', 'AssertionError', 'OSError'}
    name = type(error).__name__
    result = {'exception_type': name if name in allowed else 'Exception'}
    filenames = {'meta_browser.py', 'native_worker.py', 'native_dispatch.py', 'native_runner.py'}
    frames = [frame for frame in traceback.extract_tb(error.__traceback__)
              if Path(frame.filename).name in filenames]
    if frames:
        frame = frames[-1]
        result['code_location'] = Path(frame.filename).name + ':' + str(frame.lineno)
    return result


def shutdown_requested(_signal, _frame):
    # Unwind tick's finally block so Docker shutdown closes worker-owned pages.
    raise KeyboardInterrupt


def error_backoff_seconds(local):
    # Pending reconciliation observes the same durable correlation. It is not
    # permission to dispatch again; the dispatcher retains that invariant.
    if local.get('error') == 'checkpoint_pending_reconciliation':
        checkpoints = local.get('checkpoints', {})
        if any(job.get('phase') in {'dispatch_intent', 'accepted'}
               for job in checkpoints.values() if isinstance(job, dict)):
            return 60
    return min(21600, 300 * 2 ** min(6, max(0, local.get('failure_count', 1) - 1)))


def tick(config, state_path, context, enabled=False):
    now=dt.datetime.now(IST)
    rows=read_api(config,'drafts',{'batchId':BATCH}).get('drafts')
    if not isinstance(rows,list):
        raise NativeFailure('draft_status_unavailable')
    state=json.loads(state_path.read_text()) if state_path.exists() else {'items':{}}
    reconcile_recorded_publications(rows,state)
    state['last_checked_at']=int(time.time())
    selected=candidates(rows,now)
    state['approved_upcoming_count']=len(selected)
    due=publication_candidates(rows,now)
    state['publication_reconciliation_count']=len(due)
    selected=due+selected
    state['active_item_ids']=[row['externalId'] for row in selected]
    state['enabled']=enabled
    def save():
        # Long browser/workflow reconciliation is still live work. Persist its
        # heartbeat with the checkpoint, not only at the start of a whole batch.
        state['last_checked_at']=int(time.time())
        write_state(state_path,state)
    if not enabled:
        save()
        return
    if state.get('browser_retry_after', 0) > time.time():
        save()
        return
    from scheduler.meta_browser import MetaBrowser
    token=None
    browser_checks=0
    due_ids={row['externalId'] for row in due}
    for row in sorted(selected, key=lambda row: (0 if row['externalId'] in due_ids else
            2 if (row.get('nativeHandoff') or {}).get('state') == 'scheduled' else 1,
            state['items'].get(row['externalId'],{}).get('last_attempt_at',0))):
        identifier=row['externalId']
        if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,199}',identifier):
            raise NativeFailure('invalid_item')
        local=state['items'].setdefault(identifier,{})
        if row not in due and not state.get('browser_block_reason') and recently_verified(row,local,time.time()):
            continue
        if local.get('error') and local.get('last_attempt_at',0)>time.time()-error_backoff_seconds(local):
            continue
        # Bound browser traffic per minute; rotate toward least recently tried
        # items on subsequent ticks without changing approval or submission state.
        if browser_checks >= 3:
            break
        browser_checks += 1
        local['last_attempt_at']=int(time.time())
        browser=None
        def refresh():return read_api(config,'native-package',{'batchId':BATCH,'externalId':identifier})
        try:
            packet=refresh()
            if token is None:token=auth(config)
            dispatcher=CheckpointDispatcher(token,local,lambda _:save())
            browser=MetaBrowser(context,Path('/tmp/funzug-native')/identifier)
            if row in due:
                verify_delivery_package(packet, browser)
                outcome=browser.inspect_publication(packet)
                dispatcher('published',identifier,outcome)
                status='published'
            else:
                status=advance(packet,local,browser,dispatcher,lambda _:save(),refresh,now)
            local.pop('error',None)
            local.pop('error_diagnostics',None)
            local.pop('failure_count',None)
            if status=='scheduled':local['last_verified_at']=int(time.time())
            local['status']=status
            if status in {'scheduled', 'published'}:
                state.pop('browser_retry_after', None)
                state.pop('browser_block_reason', None)
                state['browser_failure_streak'] = 0
        except NativeFailure as error:
            local['failure_count']=local.get('failure_count',0)+1
            # Only controller-defined codes are retained; never exception bodies
            # from HTTP, browser, authentication or package decoding libraries.
            local['error']=str(error)
            local.pop('error_diagnostics',None)
            if str(error) == 'meta_temporarily_blocked':
                defer_browser(state, str(error), time.time())
        except Exception as error:
            local['failure_count']=local.get('failure_count',0)+1
            local['error']='native_worker_check_failed'
            local['error_diagnostics']=safe_error_diagnostics(error)
            diagnostics = local['error_diagnostics']
            if diagnostics.get('exception_type') == 'TimeoutError' and diagnostics.get('code_location', '').startswith('meta_browser.py:'):
                state['browser_failure_streak'] = state.get('browser_failure_streak', 0) + 1
                if state['browser_failure_streak'] >= 2:
                    defer_browser(state, 'meta_planner_unavailable', time.time())
        finally:
            if browser:
                try:browser.close()
                except Exception:pass
            save()
        if (state.get('browser_retry_after', 0) > time.time()
                or local.get('error') == 'checkpoint_pending_reconciliation'):
            # The shared GitHub queue allows only one pending writer. Finish
            # observing this durable correlation before queuing another item.
            # Otherwise later jobs can cancel earlier submission checkpoints.
            break

    # A quiet poll still proves liveness when all schedules were recently
    # verified or there are no upcoming approvals.
    save()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default='/run/secrets/config.json')
    parser.add_argument('--state',default='/state/native-worker.json')
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    config=json.loads(Path(args.config).read_text())
    enabled=os.environ.get('FUNZUG_NATIVE_BROWSER_ENABLED')=='1'
    path=Path(args.state)
    if not enabled:
        tick(config,path,None,False)
        return
    from playwright.sync_api import sync_playwright
    endpoint=os.environ.get('FUNZUG_BROWSER_CDP','http://127.0.0.1:9222')
    if endpoint!='http://127.0.0.1:9222':
        raise NativeFailure('browser_control_must_remain_container_local')
    # A single worker owns scheduling. Docker mounts /state exclusively for it;
    # the lock prevents overlapping manual invocations in the same deployment.
    import fcntl
    signal.signal(signal.SIGTERM, shutdown_requested)
    try:
        with path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with sync_playwright() as playwright:
                browser=playwright.chromium.connect_over_cdp(endpoint)
                if len(browser.contexts)!=1:raise NativeFailure('persistent_browser_context_unavailable')
                context=browser.contexts[0]
                while True:
                    try:tick(config,path,context,True)
                    except Exception:print('Native scheduler check failed; sensitive details omitted',flush=True)
                    if args.once:return
                    time.sleep(60)
    except KeyboardInterrupt:
        return


if __name__=='__main__':main()
