import json
from pathlib import Path
import time
from scheduler.native_health import healthy


def main():
    try:
        now=time.time()
        jobs=json.loads(Path('/state/home-jobs.json').read_text())
        native=json.loads(Path('/state/native-worker.json').read_text())
        return 0 if not jobs.get('error') and now-jobs.get('last_checked_at',0)<300 and healthy(native,now) else 1
    except Exception:return 1


if __name__=='__main__':raise SystemExit(main())
