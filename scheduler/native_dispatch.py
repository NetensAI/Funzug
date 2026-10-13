"""Correlate each native checkpoint with exactly one GitHub workflow run."""
from __future__ import annotations

import json
import time
import uuid
from urllib.request import Request, build_opener

from instagram_credentials import NoRedirect
from scheduler.native_worker import NativeFailure
from scripts.renew_instagram_credential import github

WORKFLOW = 'native-meta-handoff.yml'
REPO = '/repos/NetensAI/Funzug'


class CheckpointDispatcher:
    def __init__(self, auth, state, persist):
        self.auth, self.state, self.persist = auth, state, persist

    def runs(self):
        result = github('GET', REPO + '/actions/workflows/' + WORKFLOW + '/runs?branch=main&event=workflow_dispatch&per_page=100', self.auth)
        if not isinstance(result.get('workflow_runs'), list):
            raise NativeFailure('checkpoint_status_unavailable')
        return result['workflow_runs']

    def __call__(self, action, item_id, receipt=None):
        if action not in {'reserve', 'begin', 'receipt', 'published'}:
            raise NativeFailure('unsupported_worker_checkpoint')
        if action=='published' and (not isinstance(receipt,dict) or set(receipt)!={'platform_results'} or not isinstance(receipt['platform_results'],dict) or not receipt['platform_results']):
            raise NativeFailure('publication_evidence_required')
        key = action + ':' + item_id + ':' + (receipt or {}).get('platform', '')
        jobs = self.state.setdefault('checkpoints', {})
        job = jobs.get(key)
        if job is None:
            correlation = uuid.uuid4().hex
            job = {'correlation': correlation, 'requested_at': int(time.time()), 'phase': 'dispatch_intent'}
            jobs[key] = job
            self.persist(self.state)
            inputs = {'item_id': item_id, 'action': action, 'request_id': correlation}
            if receipt:
                inputs['outcome_json' if action=='published' else 'receipt_json'] = json.dumps(receipt, separators=(',', ':'))
            body = json.dumps({'ref': 'main', 'inputs': inputs}).encode()
            request = Request('https://api.github.com' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches', data=body, method='POST', headers={'Authorization':'Bearer ' + self.auth,'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'})
            try:
                with build_opener(NoRedirect()).open(request, timeout=25) as response:
                    if response.status != 204:
                        raise NativeFailure('checkpoint_dispatch_unconfirmed')
            except Exception:
                raise NativeFailure('checkpoint_dispatch_unconfirmed') from None
            job['phase'] = 'accepted'
            self.persist(self.state)
        if job.get('phase') == 'success':
            return
        deadline = time.monotonic() + 45
        expected = f'Native Meta {action} {item_id} {job["correlation"]}'
        while time.monotonic() < deadline:
            matches = [row for row in self.runs() if row.get('display_title') == expected and row.get('actor', {}).get('login') == 'funzug-automation-netensai[bot]']
            if len(matches) > 1:
                raise NativeFailure('duplicate_checkpoint_runs')
            if matches:
                run = matches[0]
                job['run_id'] = run['id']
                self.persist(self.state)
                if run.get('status') == 'completed':
                    if run.get('conclusion') != 'success':
                        job['phase'] = 'failed'
                        self.persist(self.state)
                        raise NativeFailure('checkpoint_workflow_failed')
                    job['phase'] = 'success'
                    self.persist(self.state)
                    return
            time.sleep(3)
        # The persisted correlation is reused for observation. Dispatch is never
        # repeated because no run has appeared yet or a status request timed out.
        raise NativeFailure('checkpoint_pending_reconciliation')
