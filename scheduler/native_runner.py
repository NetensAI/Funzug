"""Dedicated native Meta worker. Disabled until explicit deployment cutover."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request

from instagram_credentials import request_json
from scheduler.native_dispatch import CheckpointDispatcher
from scheduler.native_worker import IST, NativeFailure, advance, stamp
from scheduler.runner import write_state
from scripts.renew_instagram_credential import installation_token

BATCH = 'funzug-draft-inbox-v1'
DEFAULT_API = 'https://funzug.netens.top/api/integrations/funzug'


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


def candidates(rows, now):
    result=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('status')!='approved' or row.get('publicationAuthorized') is not True or row.get('publishedAt'):
            continue
        if row.get('scheduleTimezone')!='Asia/Kolkata':
            raise NativeFailure('invalid_timezone')
        if stamp(row.get('proposedSchedule'))<=now:
            continue
        result.append(row)
    return sorted(result,key=lambda row:stamp(row['proposedSchedule']))


def tick(config, state_path, context, enabled=False):
    now=dt.datetime.now(IST)
    rows=read_api(config,'drafts',{'batchId':BATCH}).get('drafts')
    if not isinstance(rows,list):
        raise NativeFailure('draft_status_unavailable')
    state=json.loads(state_path.read_text()) if state_path.exists() else {'items':{}}
    state['last_checked_at']=int(time.time())
    selected=candidates(rows,now)
    state['approved_upcoming_count']=len(selected)
    state['enabled']=enabled
    save=lambda:write_state(state_path,state)
    if not enabled:
        save()
        return
    from scheduler.meta_browser import MetaBrowser
    token=None
    for row in selected:
        identifier=row['externalId']
        if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,199}',identifier):
            raise NativeFailure('invalid_item')
        local=state['items'].setdefault(identifier,{})
        if local.get('last_verified_at',0)>time.time()-900:
            continue
        if local.get('error') and local.get('last_attempt_at',0)>time.time()-300:
            continue
        local['last_attempt_at']=int(time.time())
        browser=None
        def refresh():return read_api(config,'native-package',{'batchId':BATCH,'externalId':identifier})
        try:
            packet=refresh()
            if token is None:token=auth(config)
            dispatcher=CheckpointDispatcher(token,local,lambda _:save())
            browser=MetaBrowser(context,Path('/tmp/funzug-native')/identifier)
            status=advance(packet,local,browser,dispatcher,lambda _:save(),refresh,now)
            local.pop('error',None)
            if status=='scheduled':local['last_verified_at']=int(time.time())
            local['status']=status
        except NativeFailure as error:
            # Only controller-defined codes are retained; never exception bodies
            # from HTTP, browser, authentication or package decoding libraries.
            local['error']=str(error)
        except Exception:
            local['error']='native_worker_check_failed'
        finally:
            if browser:
                try:browser.close()
                except Exception:pass
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


if __name__=='__main__':main()
