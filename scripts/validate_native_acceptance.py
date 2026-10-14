"""Read-only validation of the isolated owner-authorized delivery test inbox."""
import json
from pathlib import Path

import funzug_pipeline as pipeline
from scripts.brandflow_sync import payload_for
from scripts.reviewed_media import approval_fingerprint


def main():
    queue = pipeline.load_json(pipeline.ROOT / 'drafts/tests/queue.json')
    errors = pipeline.validate_draft_queue(queue)
    if errors:
        raise RuntimeError('\n'.join(errors))
    if {item['id'] for item in queue['items']} != {'funzug-test-2026-10-16-carousel','funzug-test-2026-10-16-reel'}:
        raise RuntimeError('Unexpected acceptance-test items')
    for item in queue['items']:
        if item['status'] != 'draft':
            raise RuntimeError('Acceptance fixture must remain unapproved')
        payload = payload_for(item)
        draft = payload['drafts'][0]
        print(json.dumps({'id':item['id'],'format':item['format'],'media_count':len(draft['media']),
                          'content_hash':approval_fingerprint(draft),'validated':True}))


if __name__ == '__main__':
    main()
