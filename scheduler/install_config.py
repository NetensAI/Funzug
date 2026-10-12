"""Owner-server deployment helper. Extract only the draft integration secret."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--renew-after", required=True)
    args = parser.parse_args()
    source = Path("/home/vatsal/apps/brandflow/.env")
    root = Path("/home/vatsal/apps/funzug-automation/scheduler")
    if root.resolve() != root:
        raise RuntimeError("Deployment root cannot be a symlink")
    key = "FUNZUG_DRAFT_INGEST_SECRET="
    value = next((line[len(key):].strip().strip('\"').strip("'") for line in source.read_text().splitlines() if line.startswith(key)), "")
    if len(value) < 32:
        raise RuntimeError("Draft integration is not configured")
    stamp = datetime.fromisoformat(args.renew_after)
    if stamp.utcoffset() != timedelta(hours=5, minutes=30):
        raise RuntimeError("Renewal time must use IST")
    for name in ("secrets", "state"):
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
    payload = {"key_file": "/run/secrets/github-app-key.pem", "draft_secret": value, "renew_after": int(stamp.timestamp())}
    destination = root / "secrets/config.json"
    if destination.exists():
        raise RuntimeError("Existing scheduler configuration must be inspected before replacement")
    destination.write_text(json.dumps(payload))
    destination.chmod(0o600)
    print("Scheduler configuration installed; credential values omitted")


if __name__ == "__main__":
    main()
