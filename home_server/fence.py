"""Shared environment owner fence; unknown ownership fails closed."""
import json
import os
from pathlib import Path
from urllib.request import Request
from instagram_credentials import request_json
from scripts.renew_instagram_credential import installation_token

URL='https://api.github.com/repos/NetensAI/Funzug/actions/variables/FUNZUG_EXECUTION_OWNER'


def auth(config, permissions=None):
    os.environ['FUNZUG_GH_APP_ID']='5281589'
    os.environ['FUNZUG_GH_APP_PRIVATE_KEY']=Path(config['key_file']).read_text()
    try:return installation_token(permissions)
    finally:os.environ.pop('FUNZUG_GH_APP_PRIVATE_KEY',None)


def owner(config):
    token=auth(config,{'actions':'write'})
    return request_json(Request(URL,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})).get('value')


def require_home(config):
    marker=Path('/state/execution-owner.json')
    if not marker.is_file() or json.loads(marker.read_text()).get('owner')!='home' or owner(config)!='home':
        raise RuntimeError('home_execution_fence_not_owned')
