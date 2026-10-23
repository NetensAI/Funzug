"""Single locked home scheduler: native delivery, reconciliation and renewal."""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import time
from urllib.request import Request,build_opener
from instagram_credentials import decode_bundle,verify_account,refresh_bundle,NoRedirect,request_json
from scheduler import native_runner
from home_server.storage import write_state
from home_server.checkpoints import LocalDispatcher
from home_server.fence import require_home

STATE=Path('/state/home-jobs.json')
SECRETS=Path('/state/home-secrets.json')


def alert(code):
    # Pluggable private webhook. No exception body or credential in payload.
    values=json.loads(SECRETS.read_text())
    url=values.get('FUNZUG_FAILURE_WEBHOOK_URL')
    if url and url.startswith('https://'):
        try:
            with build_opener(NoRedirect()).open(Request(url,data=json.dumps({'service':'funzug-home','code':code}).encode(),headers={'Content-Type':'application/json'}),timeout=10):pass
        except Exception:pass
    print(json.dumps({'event':'home_job_failure','code':code}),flush=True)


def credential_tick(config,jobs,now):
    if now-jobs.get('credentials_checked_at',0)<86400:return
    require_home(config)
    values=json.loads(SECRETS.read_text())
    raw=values['FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL']
    bundle=decode_bundle(raw)
    verify_account(bundle['access_token'],bundle['account_id'])
    page=values.get('FUNZUG_FACEBOOK_PAGE_TOKEN')
    if not page:raise RuntimeError('facebook_verification_credential_missing')
    record=request_json(Request('https://graph.facebook.com/v26.0/124454514239741?fields=id',headers={'Authorization':'Bearer '+page}))
    if record.get('id')!='124454514239741':raise RuntimeError('facebook_identity_verification_failed')
    if now-bundle['refreshed_at']>=7*86400:
        require_home(config)
        bundle=refresh_bundle(bundle)
        values['FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL']=json.dumps(bundle)
        write_state(SECRETS,values)
    jobs['credentials_checked_at']=now
    jobs['credential_renew_after']=bundle['refreshed_at']+7*86400
    write_state(STATE,jobs)


def main():
    config=json.loads(Path('/run/secrets/config.json').read_text())
    if not SECRETS.is_file() or SECRETS.stat().st_mode&0o777!=0o600:
        raise RuntimeError('private_credentials_unavailable')
    native_runner.auth=lambda _:config
    native_runner.write_state=write_state
    native_runner.CheckpointDispatcher=lambda credentials,state,persist:LocalDispatcher(credentials,state,persist)
    from scheduler import meta_browser
    original_browser=meta_browser.MetaBrowser
    class FencedBrowser(original_browser):
        def submit(self):
            require_home(config)
            return super().submit()
    meta_browser.MetaBrowser=FencedBrowser
    with Path('/state/native-worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser=playwright.chromium.connect_over_cdp('http://127.0.0.1:9222')
            if len(browser.contexts)!=1:raise RuntimeError('browser_context_unavailable')
            while True:
                now=int(time.time())
                jobs=json.loads(STATE.read_text()) if STATE.exists() else {}
                try:
                    require_home(config)
                    credential_tick(config,jobs,now)
                    native_runner.tick(config,Path('/state/native-worker.json'),browser.contexts[0],True)
                    jobs.update(last_checked_at=int(time.time()),error=None,backend='home')
                except Exception:
                    jobs.update(last_checked_at=int(time.time()),error='home_job_failed')
                    if now-jobs.get('last_alert_at',0)>3600:
                        alert('home_job_failed');jobs['last_alert_at']=now
                write_state(STATE,jobs)
                time.sleep(60)


if __name__=='__main__':main()
