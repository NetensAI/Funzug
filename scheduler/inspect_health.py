"""Read-only, allowlisted scheduler health output. Never dispatches jobs."""
import datetime as dt
import json
import time
from pathlib import Path

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
state = json.loads(Path('/state/scheduler.json').read_text())
config = json.loads(Path('/run/secrets/config.json').read_text())


def ist(value):
    return dt.datetime.fromtimestamp(value, IST).isoformat() if isinstance(value, (int, float)) else None


print(json.dumps({
    'last_checked_ist': ist(state.get('last_checked_at')),
    'recent_poll': time.time() - state.get('last_checked_at', 0) < 180,
    'renewal_due_ist': ist(state.get('renew_after', config.get('renew_after'))),
    'active_workflows': sorted(state.get('jobs', {}).keys()),
    'last_completed_ist': {key: ist(value) for key, value in state.get('last_completed', {}).items()},
    'error_present': bool(state.get('error')),
    'result_sync_needed': bool(state.get('sync_results_needed')),
}, indent=2))
