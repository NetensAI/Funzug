"""Exercise only result synchronization over the production HTTPS route."""
import os
import sys
import json
import re
from pathlib import Path

def main():
    key='FUNZUG_DRAFT_INGEST_SECRET='
    token=next(line[len(key):].strip().strip('"').strip("'") for line in (Path.home() / 'apps/brandflow/.env').read_text().splitlines() if line.startswith(key))
    os.environ['FUNZUG_DRAFT_INGEST_SECRET']=token
    os.environ['FUNZUG_BRANDFLOW_DRAFTS_URL']='https://funzug.netens.top/api/integrations/funzug/drafts'
    sys.path.insert(0,'/tmp/funzug-outcomes-client')
    import urllib.request
    import urllib.error
    from scripts import brandflow_sync
    original=brandflow_sync.urllib.request.urlopen
    def observed(request, **kwargs):
        print('Request route: '+request.method+' '+request.full_url)
        print('Proxy variable names: '+','.join(k for k in os.environ if 'proxy' in k.lower()))
        try:
            return original(request, **kwargs)
        except urllib.error.HTTPError as error:
            print('HTTP diagnostic: status='+str(error.code)+'; content_type='+error.headers.get('Content-Type','')+'; mitigation='+error.headers.get('cf-mitigated','none'))
            body=error.read(4096).decode(errors='replace').lower()
            print('Safe response categories: '+','.join(word for word in ['origin','unauthorized','forbidden','cloudflare','access','csrf'] if word in body))
            try:
                message=json.loads(body).get('error','')
                if isinstance(message,str):
                    message=re.sub(r'[a-z0-9_./:=+-]{24,}','[redacted]',message.replace(token.lower(),'[redacted]'))
                    print('Safe rejection reason: '+message[:160])
            except Exception:
                pass
            raise
    brandflow_sync.urllib.request.urlopen=observed
    sync_results=brandflow_sync.sync_results
    assert sync_results()==0
    os.environ.pop('FUNZUG_DRAFT_INGEST_SECRET',None)
    print('Production HTTPS result client verified. No Meta calls or approvals.')

if __name__=='__main__':
    try:
        main()
    except Exception as error:
        detail=str(error) if str(error).startswith('BrandFlow API returned HTTP ') else type(error).__name__
        raise SystemExit('Result client verification failed: '+detail)
