"""Read-only editorial warnings. Does not approve, upload, or call any API."""
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def audit(queue, history, now):
    known = set(history.get('topic_keys', []))
    seen = set()
    warnings = []
    for item in queue.get('items', []):
        reasons = []
        topic = item.get('topic_key')
        if topic in known:
            reasons.append('topic appears in saved publication/schedule history')
        if topic in seen:
            reasons.append('topic repeats within draft inbox')
        if topic:
            seen.add(topic)
        try:
            schedule = dt.datetime.fromisoformat(item.get('scheduled_at', ''))
            if schedule.tzinfo is None:
                raise ValueError('timezone missing')
            if schedule <= now:
                reasons.append('proposed time has passed; owner must choose a future IST slot')
        except (ValueError, TypeError):
            reasons.append('proposed time is missing or invalid')
        if re.search(r'\b(today|tonight|tomorrow|yesterday|this (week|month|year))\b', item.get('caption', ''), re.I):
            reasons.append('relative-date wording requires event-date and selected-slot review')
        if reasons:
            warnings.append({'id': item.get('id'), 'warnings': reasons})
    return warnings


if __name__ == '__main__':
    queue = json.loads((ROOT / 'drafts/queue.json').read_text(encoding='utf-8'))
    history = json.loads((ROOT / 'history.json').read_text(encoding='utf-8'))
    warnings = audit(queue, history, dt.datetime.now(IST))
    print(json.dumps({'checked_at_ist': dt.datetime.now(IST).isoformat(),
                      'warnings': warnings,
                      'limitations': ['Saved history only. Live Meta schedule not checked.',
                                      'No claim verification or visual inspection performed by this check.',
                                      'Warnings do not alter approval or publication state.']}, indent=2))
    raise SystemExit(1 if warnings else 0)
