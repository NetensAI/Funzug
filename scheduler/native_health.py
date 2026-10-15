"""Credential-free Docker health probe for the native scheduler."""
import json
import time
from pathlib import Path


def healthy(state, now):
    if not isinstance(state, dict) or state.get('enabled') is not True:
        return False
    if state.get('browser_block_reason'):
        return False
    checked=state.get('last_checked_at')
    if not isinstance(checked,(int,float)) or not 0<=now-checked<=300:
        return False
    items=state.get('items')
    if not isinstance(items,dict):
        return False
    active=state.get('active_item_ids',list(items))
    if not isinstance(active,list):
        return False
    for identifier in active:
        item=items.get(identifier,{})
        if not isinstance(item,dict):
            return False
        if item.get('error') not in {None,'checkpoint_pending_reconciliation'}:
            return False
        if item.get('error')=='checkpoint_pending_reconciliation':
            jobs=item.get('checkpoints',{})
            pending=[job for job in jobs.values() if job.get('phase')!='success']
            if not pending or any(now-job.get('requested_at',0)>900 for job in pending):
                return False
    return True


def main():
    try:
        state=json.loads(Path('/state/native-worker.json').read_text())
        return 0 if healthy(state,time.time()) else 1
    except Exception:
        return 1


if __name__=='__main__':
    raise SystemExit(main())
