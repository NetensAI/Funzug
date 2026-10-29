"""Readiness gate for the home cutover. Never activates an incomplete release."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import hashlib
import time
import re


class DeploymentFailure(RuntimeError):
    def __init__(self,code):self.code=code

ROOT = Path(__file__).resolve().parents[1]
BASE = Path.home() / '.local/lib/funzug-phase2'

# Runs inside the existing worker, using its existing private runtime mount.
# Only name-presence, validity booleans and approved scheduling metadata leave it.
PROBE = r'''
import datetime as dt,json,os,pathlib
from scheduler.native_runner import read_api,candidates,publication_candidates,IST
from instagram_credentials import decode_bundle,verify_account,request_json
from urllib.request import Request
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
    try:
        bundle=decode_bundle(raw)
        verify_account(bundle['access_token'],bundle['account_id'])
        values=json.loads(store.read_text())
        page=values.get('FUNZUG_FACEBOOK_PAGE_TOKEN')
        if not page:raise RuntimeError('page verification unavailable')
        identity=request_json(Request('https://graph.facebook.com/v26.0/124454514239741?fields=id',headers={'Authorization':'Bearer '+page}))
        if identity.get('id')!='124454514239741':raise RuntimeError('page identity mismatch')
        valid=True
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
    return sorted(set(failures))


def command(args,timeout=120,env=None):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env=env)
    if result.returncode:
        status=re.search(r'HTTP(?: Error| status|)?[ :]+([1-5][0-9]{2})',result.stderr)
        code='deployment_http_'+status.group(1) if status else 'deployment_command_failed'
        for text,label in [('read-only file system','readonly'),('permission denied','permission'),('no module named','missing_module'),('not found','not_found'),('failed to solve','build_failed'),('FAILED (','tests_failed')]:
            if text.lower() in result.stderr.lower():
                code+='_'+label
                break
        raise DeploymentFailure(code)
    return result.stdout


def runtime_digest():
    paths=list((ROOT/'home_server').glob('*.py'))+list((ROOT/'scheduler').glob('*.py'))
    paths += [ROOT/'home-server/Dockerfile',ROOT/'home-server/compose.yml']
    # Controller policy is part of the dry-run proof, not just runtime code.
    paths += [ROOT/'home-server/deploy.py']
    return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+p.read_bytes() for p in sorted(paths))).hexdigest()


def compose(*args, project='funzug-home'):
    env=dict(os.environ,FUNZUG_DEPLOYMENT_ROOT=str(Path.home()/'apps/funzug-automation'))
    return command(['docker','compose','-p',project,'-f',str(ROOT/'home-server/compose.yml'),*args],600,env)


def github_control(operation):
    # Fixed operations, run inside the existing mounted-key container. Only
    # ownership strings and workflow IDs leave the process, never auth values.
    program=r'''
import json,os,pathlib
from urllib.request import Request,build_opener
from urllib.error import HTTPError
from instagram_credentials import NoRedirect
from scripts.renew_instagram_credential import installation_token,github
config=json.loads(pathlib.Path('/run/secrets/config.json').read_text())
os.environ['FUNZUG_GH_APP_ID']='5281589'
os.environ['FUNZUG_GH_APP_PRIVATE_KEY']=pathlib.Path(config['key_file']).read_text()
token=installation_token({'actions':'write'} if OP=='active' else None)
os.environ.pop('FUNZUG_GH_APP_PRIVATE_KEY',None)
base='/repos/NetensAI/Funzug/environments/funzug-publish/variables'
if OP=='active':
    selected=[]
    for status in ('in_progress','queued','waiting','pending'):
        data=github('GET','/repos/NetensAI/Funzug/actions/runs?per_page=100&status='+status,token)
        if data.get('total_count',0)>100:raise RuntimeError('too many active runs')
        selected.extend(r['id'] for r in data['workflow_runs'] if r['path'] not in {'.github/workflows/test-pipeline.yml','.github/workflows/home-credential-transfer.yml'})
    print(json.dumps({'active':sorted(set(selected))}))
else:
    value=OP
    if value not in {'home','github','transition'}:raise RuntimeError('invalid owner')
    payload=json.dumps({'name':'FUNZUG_EXECUTION_OWNER','value':value}).encode()
    def send(method,path):
        request=Request('https://api.github.com'+path,data=payload,method=method,
          headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json'})
        with build_opener(NoRedirect()).open(request,timeout=25) as response:
            if response.status not in {201,204}:raise RuntimeError('owner update unconfirmed')
    try:send('PATCH',base+'/FUNZUG_EXECUTION_OWNER')
    except HTTPError as error:
        if error.code!=404:raise
        send('POST',base)
    print(json.dumps({'owner':value}))
'''
    executor='funzug-native-worker'
    inspected=json.loads(command(['docker','inspect',executor]))[0]
    prefix=['docker','exec','-i',executor]
    if not inspected['State']['Running']:
        mount=str(Path.home()/'apps/funzug-automation/scheduler/secrets')
        prefix=['docker','run','--name','funzug-home-control-'+str(time.time_ns()),
                '--network','container:funzug-meta-browser','--read-only','--user','1000:1000',
                '--cap-drop=ALL','--security-opt=no-new-privileges',
                '--mount','type=bind,src='+mount+',dst=/run/secrets,readonly',
                'funzug-native-worker:repair-20261023053035']
    return json.loads(command(prefix+['python','-c','OP='+repr(operation)+'\n'+program],90))


def rollback():
    directory=Path.home()/'apps/funzug-automation/scheduler/native-state'
    queue=directory/'home-queue.json'
    native=json.loads((directory/'native-worker.json').read_text())
    if not queue.exists() or json.loads(queue.read_text())!=json.loads((ROOT/'queue.json').read_text()):
        return {'result':'rollback_refused','failed_checks':['home_queue_requires_emergency_export_and_reconciliation']}
    for identifier in native.get('active_item_ids',[]):
        if native['items'].get(identifier,{}).get('status') not in {'scheduled','published'}:
            return {'result':'rollback_refused','failed_checks':['unsettled_native_intent']}
    github_control('transition')
    command(['docker','stop','--timeout','60','funzug-home-worker'])
    command(['docker','update','--restart=no','funzug-home-worker'])
    private_write(directory/'execution-owner.json',{'owner':'github'})
    github_control('github')
    command(['docker','update','--restart=unless-stopped','scheduler-scheduler-1','funzug-native-worker'])
    command(['docker','start','scheduler-scheduler-1','funzug-native-worker'])
    return {'result':'github_emergency_owner_restored','owner':'github','rollback_available':True}


def private_write(path,value):
    if path.is_symlink():raise RuntimeError('symlink refused')
    temporary=path.with_name(path.name+'.stage-'+str(time.time_ns()))
    with temporary.open('x') as handle:
        os.fchmod(handle.fileno(),0o600);json.dump(value,handle)
    os.replace(temporary,path)


def runner_command_valid(argv):
    # Accept only direct module execution, including unbuffered Python.
    return argv in (["python", "-m", "home_server.runner"],
                    ["python3", "-m", "home_server.runner"],
                    ["python", "-u", "-m", "home_server.runner"],
                    ["python3", "-u", "-m", "home_server.runner"])


def dry_run():
    if (BASE/'cutover.json').is_file():
        home=json.loads(command(['docker','inspect','funzug-home-worker']))[0]
        old=json.loads(command(['docker','inspect','funzug-native-worker','scheduler-scheduler-1']))
        checks=[]
        if not runner_command_valid(home['Config'].get('Cmd')):
            checks.append('home_command_unexpected')
        if home['Config'].get('Entrypoint'):
            checks.append('inherited_entrypoint_present')
        proof=json.loads(command(['docker','exec','funzug-home-worker','python','-c',
            'import json;from scheduler.meta_browser import MetaBrowser;print(json.dumps({"patched":hasattr(MetaBrowser,"publication_heading")}))']))
        if not proof.get('patched'):checks.append('runtime_publication_patch_missing')
        marker=BASE/'home-update.json'
        return {'result':'home_health_status','healthy':home['State'].get('Health',{}).get('Status')=='healthy',
                'revision':json.loads(marker.read_text()).get('revision') if marker.is_file() else None,
                'failed_checks':checks,
                'owner':'home','legacy_dispatcher_stopped':not any(c['State']['Running'] for c in old),
                'duplicate_executors':sum(bool(c['State']['Running']) for c in old)}
    compose('config','--quiet')
    compose('build')
    completed = subprocess.run(
        ['docker', 'exec', '-i', 'funzug-native-worker', 'python', '-'],
        input=PROBE, text=True, capture_output=True, timeout=90)
    if completed.returncode:
        return {'result': 'dry_run_blocked', 'dry_run_passed': False,
                'failed_checks': ['private_mount_probe_unavailable']}
    probe = json.loads(completed.stdout)
    queue = json.loads((ROOT / 'queue.json').read_text())
    failed = assess(queue, probe)
    # Run actual local checkpoint/fence tests offline in the built image. No
    # production mounts and no network are provided to this test container.
    test_name='funzug-home-dry-test-'+str(time.time_ns())
    command(['docker','run','--name',test_name,'--network=none','--read-only',
             '--tmpfs','/tmp:uid=1000,gid=1000,mode=0700','--cap-drop=ALL',
             '--security-opt=no-new-privileges','funzug-home-worker:local',
             'python','-m','unittest','discover','-s','tests','-p','test_home_executor.py'],180)
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
    private_write(BASE/'last-dry-run.json',dict(result,runtime_digest=runtime_digest(),checked_at=int(time.time())))
    return result


def update_home():
    """Explicit repair deployment, never invoked by metadata-only monitoring.

    Preserve both old container and all mounted state. A distinct Compose
    project prevents Compose from removing/recreating the retained backup.
    Home ownership stays unchanged; stop/wait plus the existing flock exclude
    overlap. No publication records, cooldowns or submission intents are reset.
    """
    directory=Path.home()/'apps/funzug-automation/scheduler/native-state'
    native=json.loads((directory/'native-worker.json').read_text())
    if native.get('browser_block_reason')=='meta_temporarily_blocked':
        return {'result':'home_update_blocked','failed_checks':['browser_restricted']}
    marker=json.loads((directory/'execution-owner.json').read_text())
    if marker.get('owner')!='home':
        return {'result':'home_update_blocked','failed_checks':['home_owner_required']}
    old=json.loads(command(['docker','inspect','funzug-native-worker','scheduler-scheduler-1']))
    if any(c['State']['Running'] for c in old):
        return {'result':'home_update_blocked','failed_checks':['competing_executor']}
    # Public code and isolated tests only, with no credentials or production
    # mounts. A failing build/test never stops the existing worker.
    revision=command(['git','-C',str(ROOT),'rev-parse','HEAD']).strip()
    project='funzug-home-'+revision[:12]
    compose('config','--quiet',project=project)
    compose('build',project=project)
    command(['docker','run','--name','funzug-home-repair-test-'+str(time.time_ns()),
             '--network=none','--read-only','--tmpfs','/tmp:uid=1000,gid=1000,mode=0700',
             '--cap-drop=ALL','--security-opt=no-new-privileges','funzug-home-worker:local',
             'python','-m','unittest','tests.test_home_executor','tests.test_native_runner',
             'tests.test_native_browser_cleanup','tests.test_home_readiness'],180)
    # Preserve an unavailable-Planner timer unchanged. The replacement reads
    # the same state and must wait for it; deploying code is not Meta access.
    # A positively identified actual block still refuses the update.
    native=json.loads((directory/'native-worker.json').read_text())
    if native.get('browser_block_reason')=='meta_temporarily_blocked':
        return {'result':'home_update_blocked','failed_checks':['browser_restricted']}
    backup='funzug-home-worker-backup-'+str(time.time_ns())
    command(['docker','stop','--timeout','90','funzug-home-worker'])
    current=json.loads(command(['docker','inspect','funzug-home-worker']))[0]
    if current['State']['Running']:raise RuntimeError('home stop unconfirmed')
    command(['docker','update','--restart=no','funzug-home-worker'])
    command(['docker','rename','funzug-home-worker',backup])
    # Do not remove any container, including on a failed startup. All state
    # remains mounted in place; subsequent health checks expose any failure.
    compose('up','-d','--no-build',project=project)
    private_write(BASE/'home-update.json',{'revision':revision,'backup':backup,
                  'project':project,'updated_at':int(time.time())})
    return {'result':'home_update_started','revision':revision,'owner':'home',
            'legacy_dispatcher_stopped':True,'duplicate_executors':0}


def cutover():
    if (BASE/'cutover.json').is_file():
        return update_home()
    proof=json.loads((BASE/'last-dry-run.json').read_text())
    if not proof.get('dry_run_passed') or proof.get('runtime_digest')!=runtime_digest() or time.time()-proof.get('checked_at',0)>3600:
        return {'result':'activation_refused','failed_checks':['fresh_matching_dry_run_required']}
    # The staged revision must include the disabled triggers and explicit
    # GitHub-owner guard. No recurring trigger is changed by this controller.
    workflow_dir=ROOT/'.github/workflows'
    production=[p for p in workflow_dir.glob('*.yml') if p.is_file() and p.name not in {'test-pipeline.yml','home-credential-transfer.yml'}]
    for path in production:
        source=path.read_text()
        if '\n  schedule:' in source or '\n  push:' in source or 'test "$FUNZUG_EXECUTION_OWNER" = github' not in source:
            return {'result':'activation_refused','failed_checks':['github_workflows_not_fenced_and_manual_only']}
    import urllib.request
    public=json.load(urllib.request.urlopen('https://api.github.com/repos/NetensAI/Funzug/commits/main',timeout=25))
    revision=command(['git','-C',str(ROOT),'rev-parse','HEAD']).strip()
    if public['sha']!=revision:return {'result':'activation_refused','failed_checks':['release_is_not_current_main']}
    state_dir=Path.home()/'apps/funzug-automation/scheduler/native-state'
    native=json.loads((state_dir/'native-worker.json').read_text())
    if native.get('browser_block_reason') or native.get('browser_retry_after',0)>time.time():
        return {'result':'activation_refused','failed_checks':['browser_restricted']}
    for identifier in native.get('active_item_ids',[]):
        item=native['items'].get(identifier,{})
        if item.get('error') or item.get('status') not in {'scheduled','published'}:
            return {'result':'activation_refused','failed_checks':['unsettled_native_intent']}
    github_control('transition')
    for _ in range(24):
        if not github_control('active')['active']:break
        time.sleep(10)
    else:return {'result':'cutover_waiting','owner':'transition','failed_checks':['github_jobs_not_drained']}
    command(['docker','stop','--timeout','60','scheduler-scheduler-1','funzug-native-worker'])
    command(['docker','update','--restart=no','scheduler-scheduler-1','funzug-native-worker'])
    if github_control('active')['active']:
        return {'result':'cutover_waiting','owner':'transition','failed_checks':['late_github_writer_detected']}
    queue=state_dir/'home-queue.json'
    if not queue.exists():private_write(queue,json.loads((ROOT/'queue.json').read_text()))
    history=state_dir/'home-history.json'
    if not history.exists():private_write(history,json.loads((ROOT/'history.json').read_text()))
    private_write(state_dir/'execution-owner.json',{'owner':'home','revision':revision})
    github_control('home')
    # Initial deployment only. Never let Compose delete/recreate a preexisting
    # container under the standing preserve-everything rule.
    existing=subprocess.run(['docker','inspect','funzug-home-worker'],capture_output=True)
    if existing.returncode==0:return {'result':'activation_refused','owner':'home','failed_checks':['home_container_already_exists']}
    compose('up','-d','--no-build')
    for _ in range(24):
        info=json.loads(command(['docker','inspect','funzug-home-worker']))[0]
        if info['State'].get('Health',{}).get('Status')=='healthy':
            private_write(BASE/'cutover.json',{'revision':revision,'completed_at':int(time.time()),'owner':'home'})
            return {'result':'home_cutover_verified','revision':revision,'owner':'home','healthy':True,
                    'github_schedules_disabled':True,'legacy_dispatcher_stopped':True,
                    'duplicate_executors':0,'rollback_available':True}
        time.sleep(10)
    return {'result':'home_started_health_not_verified','owner':'home','healthy':False,
            'failed_checks':['home_health_not_confirmed']}


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
    elif operation=='cutover':
        result=cutover()
    elif operation=='rollback':
        result=rollback()
    else:
        raise RuntimeError('unsupported operation')
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import traceback
        frames=[frame for frame in traceback.extract_tb(error.__traceback__) if Path(frame.filename).name=='deploy.py']
        callers=[frame for frame in frames if frame.name!='command']
        location='deploy_line_'+str(callers[-1].lineno) if callers else 'deployment_location_unavailable'
        kind=type(error).__name__
        if kind not in {'RuntimeError','TypeError','KeyError','FileNotFoundError','HTTPError','PermissionError','TimeoutExpired','ValueError'}:kind='Exception'
        print(json.dumps({'result': 'readiness_failed', 'dry_run_passed': False,
                          'failed_checks': [error.code if isinstance(error,DeploymentFailure) else 'deployment_error_'+kind,location]}))
