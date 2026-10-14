"""One-time private ingestion of the two owner-authorized acceptance drafts."""
import json
import os
from pathlib import Path
from scripts import brandflow_sync


def main():
    config = json.loads(Path('/run/secrets/config.json').read_text())
    os.environ['FUNZUG_DRAFT_INGEST_SECRET'] = config['draft_secret']
    try:
        return brandflow_sync.sync_pending(acceptance_tests=True)
    finally:
        os.environ.pop('FUNZUG_DRAFT_INGEST_SECRET', None)


if __name__ == '__main__':
    raise SystemExit(main())
