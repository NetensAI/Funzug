"""Read-only comparison of pending BrandFlow fingerprints and local drafts."""
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
        statuses = sync.api_status(sync.api_url(), token)
        drafts = sync.pipeline.load_json(sync.pipeline.DRAFT_QUEUE_PATH)['items']
        count = 0
        for item in drafts:
            row = statuses.get(item['id'], {})
            if row.get('status') != 'pending_review':
                continue
            sync.require_matching_approved_content(item, row)
            count += 1
        if count != 7:
            raise ValueError('Unexpected pending count')
        print(f'Exact caption, claims, sources, platforms and image fingerprints match: {count}. Read-only; no approvals or Meta calls.')
    finally:
        os.environ.pop('FUNZUG_DRAFT_INGEST_SECRET', None)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Content fingerprint verification failed: ' + type(error).__name__)
