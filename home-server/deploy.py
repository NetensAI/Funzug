"""Readiness gate for the home cutover. Never activates an incomplete release."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = Path.home() / '.local/lib/funzug-phase2'

# Runs inside the existing worker, using its existing private runtime mount.
# Only name-presence, validity booleans and approved scheduling metadata leave it.
PROBE = r'''
import datetime as dt,json,os,pathlib
from scheduler.native_runner import read_api,candidates,publication_candidates,IST
from instagram_credentials import decode_bundle
config=json.loads(pathlib.Path('/run/secrets/config.json').read_text())
rows=read_api(config,'drafts',{'batchId':'funzug-draft-inbox-v1'})['drafts']
now=dt.datetime.now(IST)
selected=candidates(rows,now)
missing=[]
raw=os.environ.get('FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL') or config.get('FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL')
path=pathlib.Path('/run/secrets/FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL')
if not raw and path.is_file(): raw=path.read_text()
store=pathlib.Path('/state/home-secrets.json')
if not raw and store.is_file(): raw=json.loads(store.read_text()).get('FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL')
valid=False
if raw:
    try: decode_bundle(raw);valid=True
    except Exception: pass
else: missing.append('FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL')
print(json.dumps({'missing_secret_names':missing,'credential_valid':valid,
 'renewal_storage_writable':store.is_file() and os.access(store,os.W_OK) and (store.stat().st_mode&0o777)==0o600,
 'due_reconciliation_count':len(publication_candidates(rows,now)),
 'rows':[{'id':r['externalId'],'slot':r['proposedSchedule'],
          'handoff':r.get('nativeHandoff')} for r in selected]}))
'''


def assess(queue, probe):
    failures = []
    expected = {row['id']: row for row in queue['items']}
    for row in probe['rows']:
        item = expected.get(row['id'])
        if item is None:
            failures.append('approved_id_missing_from_queue')
            continue
        left = dt.datetime.fromisoformat(row['slot'].replace('Z', '+00:00'))
        right = dt.datetime.fromisoformat(item['scheduled_at'].replace('Z', '+00:00'))
        if left != right:
            failures.append('owner_slot_mismatch')
        if row.get('handoff') != item.get('native_handoff'):
            failures.append('native_handoff_mismatch')
    if probe.get('missing_secret_names'):
        failures.append('local_renewal_credential_missing')
    elif not probe.get('credential_valid'):
        failures.append('local_renewal_credential_invalid')
    if not probe.get('renewal_storage_writable'):
        failures.append('renewal_output_store_not_provisioned')
    # This first release deliberately cannot activate a partially implemented
    # executor. Passing a data comparison is not a full migration dry-run.
    failures.extend(('local_executor_not_staged', 'cross_executor_fence_not_staged'))
    return sorted(set(failures))


def dry_run():
    completed = subprocess.run(
        ['docker', 'exec', '-i', 'funzug-native-worker', 'python', '-'],
        input=PROBE, text=True, capture_output=True, timeout=90)
    if completed.returncode:
        return {'result': 'dry_run_blocked', 'dry_run_passed': False,
                'failed_checks': ['private_mount_probe_unavailable']}
    probe = json.loads(completed.stdout)
    queue = json.loads((ROOT / 'queue.json').read_text())
    failed = assess(queue, probe)
    report_id = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).strftime('%Y%m%d-%H%M%S-IST')
    result = {'result': 'dry_run_blocked' if failed else 'dry_run_passed',
              'dry_run_passed': not failed,
              'missing_secret_names': probe['missing_secret_names'],
              'failed_checks': failed, 'report_id': report_id}
    directory = BASE / 'reports'
    if directory.is_symlink():
        raise RuntimeError('unsafe report directory')
    directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / (report_id + '.json')).open('x') as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(result, handle)
    return result


def main():
    operation = sys.argv[1] if len(sys.argv) == 2 else ''
    if operation == 'dry-run':
        result = dry_run()
    elif operation == 'cutover' and not (Path.home()/'apps/funzug-automation/scheduler/native-state/home-secrets.json').exists():
        source=(ROOT/'scripts/home_credential_transfer.py').read_text()
        program='namespace={"__name__":"home_transfer"}\nexec('+repr(source)+',namespace)\nnamespace["import_latest"]()\n'
        completed=subprocess.run(['docker','exec','-i','funzug-native-worker','python','-'],
                                 input=program,text=True,capture_output=True,timeout=120)
        if completed.returncode:
            result={'result':'credential_import_failed','failed_checks':['encrypted_migration_import_failed_details_omitted']}
        else:
            result=json.loads(completed.stdout)
    elif operation in {'cutover', 'rollback'}:
        result = {'result': 'activation_refused', 'dry_run_passed': False,
                  'failed_checks': ['complete_executor_and_verified_dry_run_required']}
    else:
        raise RuntimeError('unsupported operation')
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'result': 'readiness_failed', 'dry_run_passed': False,
                          'failed_checks': ['readiness_error_details_omitted']}))
