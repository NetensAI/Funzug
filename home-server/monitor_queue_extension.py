"""Read-only topic inventory. Never export captions, media, or credentials."""
import json
import re
from pathlib import Path


def summarize(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32000000:
        return {'available': False}
    data = json.loads(path.read_text())
    items = data.get('items') if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {'available': False}
    rows = []
    for item in items:
        if not isinstance(item, dict):
            return {'available': False}
        identifier = item.get('id', '')
        if not isinstance(identifier, str) or not re.fullmatch(r'funzug-[a-z0-9-]{1,180}', identifier):
            return {'available': False}
        row = {'id': identifier}
        if item.get('status') in {'draft', 'approved', 'scheduled', 'published', 'rejected', 'cancelled', 'pending_review', 'submitting'}:
            row['status'] = item['status']
        topics = item.get('topic_keys', [])
        if isinstance(topics, list):
            row['topic_keys'] = [v for v in topics if isinstance(v, str) and re.fullmatch(r'[a-z0-9-]{1,180}', v)]
        rows.append(row)
    return {'available': True, 'source': 'private_home_queue', 'count': len(rows), 'items': rows}


def install():
    base = Path.home() / '.local/lib/funzug-monitor'
    target = base / 'monitor_health.py'
    backup = base / 'monitor_health_before_queue.py'
    extension = base / 'monitor_queue_extension.py'
    if any(p.is_symlink() for p in (base, target, backup, extension)) or not target.is_file():
        raise RuntimeError('monitor_installation_invalid')
    original = target.read_text()
    marker = '# Funzug queue topic extension v1'
    if marker not in original:
        if backup.exists():
            raise RuntimeError('monitor_backup_already_exists')
        backup.write_text(original)
        backup.chmod(0o600)
        anchor = "print(json.dumps(collect(), indent=2))"
        if original.count(anchor) != 1:
            raise RuntimeError('monitor_entrypoint_unrecognized')
        replacement = "output = collect()\n        from monitor_queue_extension import summarize\n        try:\n            output['live_queue'] = summarize(ROOT / 'scheduler/native-state/home-queue.json')\n        except Exception:\n            output['live_queue'] = {'available': False}\n        print(json.dumps(output, indent=2))"
        updated = marker + '\n' + original.replace(anchor, replacement)
        compile(updated, str(target), 'exec')
    else:
        updated = original
    extension.write_text(Path(__file__).read_text())
    extension.chmod(0o600)
    temporary = base / 'monitor_health.queue-update'
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError('monitor_update_path_exists')
    temporary.write_text(updated)
    temporary.chmod(0o600)
    temporary.replace(target)
    return {'result': 'read_only_queue_monitor_installed', 'owner': 'home'}
