"""Owner-authorized replay of recorded results only. Never calls Meta."""
import json
from pathlib import Path
import urllib.request
import urllib.error

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def main():
    key='FUNZUG_DRAFT_INGEST_SECRET='
    lines=(Path.home() / 'apps/brandflow/.env').read_text().splitlines()
    token=next(line[len(key):].strip().strip('"').strip("'") for line in lines if line.startswith(key))
    assert len(token)>=32
    queue=json.loads(Path('/tmp/funzug-results-verification.json').read_text())
    item=next(x for x in queue['items'] if x['status']=='published')
    assert set(item['platform_results'])=={'facebook','instagram'}
    payload={'batchId':'funzug-draft-inbox-v1','externalId':item['id'],'platformResults':{p:{'status':'published','postId':r['post_id'],'publishedAt':r['published_at']} for p,r in item['platform_results'].items()}}
    opener=urllib.request.build_opener(NoRedirect)
    def send(data):
        request=urllib.request.Request('http://127.0.0.1:3000/api/integrations/funzug/outcomes',data=json.dumps(data).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
        with opener.open(request,timeout=20) as response:
            assert response.status==200
            return json.loads(response.read())
    first=send(payload)
    second=send(payload)
    assert first['complete'] is True and second['complete'] is True and second['unchanged'] is True
    conflict=json.loads(json.dumps(payload))
    conflict['platformResults']['facebook']['postId']='conflicting-test-id-never-published'
    try:
        send(conflict)
        raise AssertionError('Conflicting ID was accepted')
    except urllib.error.HTTPError as error:
        assert error.code==409
    print('Existing recorded results accepted; repeated replay unchanged; conflicting ID rejected; no Meta calls.')

if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Outcome verification failed; sensitive details omitted.')
