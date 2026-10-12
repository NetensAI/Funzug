"""Operator-only pending draft correction. No approval or publishing invocation."""
import os
import sys
from pathlib import Path


def main():
    sys.path.insert(0, '/tmp/funzug-outcomes-client')
    from scripts import brandflow_sync as sync
    key = 'FUNZUG_DRAFT_INGEST_SECRET='
    token = next(line[len(key):].strip().strip('"').strip("'") for line in Path('/home/vatsal/apps/brandflow/.env').read_text().splitlines() if line.startswith(key))
    os.environ['FUNZUG_DRAFT_INGEST_SECRET'] = token
    os.environ['FUNZUG_BRANDFLOW_DRAFTS_URL'] = 'https://funzug.netens.top/api/integrations/funzug/drafts'
    try:
        before = sync.api_status(sync.api_url(), token)
        reviewed = {k: v for k, v in before.items() if v.get('status') != 'pending_review'}
        sync.sync_pending(update_pending=True)
        after = sync.api_status(sync.api_url(), token)
        if any(after.get(k) != v for k, v in reviewed.items()):
            raise RuntimeError('Reviewed draft status changed concurrently; inspect before proceeding')
        pending = [v for v in after.values() if v.get('status') == 'pending_review']
        if any(v.get('publicationAuthorized') is not False or v.get('publishedAt') for v in pending):
            raise RuntimeError('Pending draft state is inconsistent')
        print(f'Pending drafts remain unauthorized: {len(pending)}. Reviewed states unchanged. No Meta calls.')
    finally:
        os.environ.pop('FUNZUG_DRAFT_INGEST_SECRET', None)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        detail = str(error) if str(error).startswith('BrandFlow API returned HTTP ') else type(error).__name__
        raise SystemExit('Pending revision transfer failed: ' + detail)
