"""Mini PC event scheduler. Dispatches existing approval-gated workflows only."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import Request, build_opener

from instagram_credentials import NoRedirect, request_json
from scripts.renew_instagram_credential import github, installation_token

SYNC = "brandflow-draft-approval.yml"
PUBLISH = "publish-approved.yml"
RENEW = "renew-instagram-credential.yml"
ALLOWED = {SYNC, PUBLISH, RENEW}


def approved_rows(rows: list, now: int) -> tuple[str, bool]:
    selected = []
    due = False
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "approved" or row.get("publicationAuthorized") is not True or row.get("publishedAt"):
            continue
        # Native Meta handoffs are scheduled in Business Suite, not via the
        # Graph API publisher. Keep them out of both due dispatches and the
        # scheduler's approval signature so a native slot cannot trigger a
        # second publishing path after its time passes.
        if row.get("nativeHandoff") is not None:
            continue
        if row.get("scheduleTimezone") != "Asia/Kolkata":
            raise RuntimeError("Approved schedule timezone is invalid")
        stamp = datetime.fromisoformat(row["proposedSchedule"].replace("Z", "+00:00"))
        # Postgres serializes timestamptz as UTC; the separate timezone field is authoritative.
        if stamp.tzinfo is None:
            raise RuntimeError("Approved schedule is missing a timezone")
        selected.append({k: row.get(k) for k in ("externalId", "proposedSchedule", "reviewedAt", "reviewedBy")})
        due = due or stamp.timestamp() <= now
    signature = hashlib.sha256(json.dumps(sorted(selected, key=lambda x: x["externalId"]), sort_keys=True).encode()).hexdigest()
    return signature, due


def write_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True))
    tmp.chmod(0o600)
    tmp.replace(path)


def workflow_runs(workflow: str, auth: str) -> list:
    data = github("GET", f"/repos/NetensAI/Funzug/actions/workflows/{workflow}/runs?branch=main&event=workflow_dispatch&per_page=10", auth)
    rows = data.get("workflow_runs")
    if not isinstance(rows, list):
        raise RuntimeError("Workflow run status is unavailable")
    return rows


def dispatch(workflow: str, auth: str, inputs: dict | None = None) -> None:
    if workflow not in ALLOWED:
        raise RuntimeError("Workflow is outside the scheduler scope")
    body = {"ref": "main"}
    if inputs:
        body["inputs"] = inputs
    request = Request(f"https://api.github.com/repos/NetensAI/Funzug/actions/workflows/{workflow}/dispatches",
        data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": "Bearer " + auth, "Accept": "application/vnd.github+json",
            "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    with build_opener(NoRedirect()).open(request, timeout=25) as response:
        if response.status != 204:
            raise RuntimeError("Workflow dispatch was not accepted")


def tick(config: dict, path: Path, dry_run: bool = False) -> None:
    now = int(time.time())
    state = json.loads(path.read_text()) if path.exists() else {"jobs": {}, "synced_signature": ""}
    url = "http://127.0.0.1:3000/api/integrations/funzug/drafts?batchId=funzug-draft-inbox-v1"
    drafts = request_json(Request(url, headers={"Authorization": "Bearer " + config["draft_secret"]})).get("drafts")
    if not isinstance(drafts, list):
        raise RuntimeError("BrandFlow status is unavailable")
    signature, due = approved_rows(drafts, now)
    state["last_checked_at"] = now
    if dry_run:
        print(f"Scheduler diagnostic: approval_change={signature != state['synced_signature']}; approved_post_due={due}; no workflow dispatched", flush=True)
        return
    renewal_at = state.get("renew_after", config.get("renew_after"))
    if not state["jobs"] and not state.get("error") and signature == state["synced_signature"] and not due and not state.get("sync_results_needed") and (not renewal_at or now < renewal_at):
        write_state(path, state)
        return
    os.environ["FUNZUG_GH_APP_ID"] = "5281589"
    os.environ["FUNZUG_GH_APP_PRIVATE_KEY"] = Path(config["key_file"]).read_text()
    try:
        auth = installation_token({"actions": "write"})
    finally:
        os.environ.pop("FUNZUG_GH_APP_PRIVATE_KEY", None)
    runs = {workflow: workflow_runs(workflow, auth) for workflow in ALLOWED}
    blocked = set()
    for workflow, job in list(state["jobs"].items()):
        matches = [r for r in runs[workflow] if r["id"] > job["baseline"] and r.get("actor", {}).get("login") == "funzug-automation-netensai[bot]"]
        if not matches:
            blocked.add(workflow)
            if now - job["requested_at"] > 600:
                state["error"] = "Dispatch acceptance is ambiguous; manual audit required for " + workflow
            continue
        run = min(matches, key=lambda r: r["id"])
        job["run_id"] = run["id"]
        if run["status"] != "completed":
            blocked.add(workflow)
            continue
        state.setdefault("last_completed", {})[workflow] = now
        # Preserve completed platform results even if another platform or the
        # publisher's final dashboard sync failed. This does not retry posts.
        if workflow == PUBLISH:
            state["sync_results_needed"] = True
        if run.get("conclusion") == "success":
            if state.get("error", "").startswith(workflow + " failed;"):
                state.pop("error", None)
            state.get("cooldown_until", {}).pop(workflow, None)
            if workflow == SYNC:
                state["synced_signature"] = job["signature"]
            elif workflow == RENEW:
                state["renew_after"] = now + 7 * 86400
        else:
            state["error"] = workflow + " failed; run_id=" + str(run["id"])
            state.setdefault("cooldown_until", {})[workflow] = now + 300
            print(state["error"], flush=True)
        del state["jobs"][workflow]
    error = state.get("error")
    if isinstance(error, str):
        for workflow, records in runs.items():
            prefix = workflow + " failed; run_id="
            if not error.startswith(prefix):
                continue
            try:
                failed_run_id = int(error[len(prefix):])
            except ValueError:
                break
            recovered = any(
                isinstance(run.get("id"), int)
                and run["id"] > failed_run_id
                and run.get("status") == "completed"
                and run.get("conclusion") == "success"
                and run.get("actor", {}).get("login") == "funzug-automation-netensai[bot]"
                for run in records
            )
            if recovered:
                state.pop("error", None)
                state.get("cooldown_until", {}).pop(workflow, None)
            break
    for workflow, records in runs.items():
        if any(r.get("status") != "completed" for r in records):
            blocked.add(workflow)
    requested = []
    last = state.get("last_requested", {})
    if signature != state["synced_signature"] or state.get("sync_results_needed") or (due and now - last.get(SYNC, 0) >= 300):
        requested.append((SYNC, {}))
    elif due and now - last.get(PUBLISH, 0) >= 300:
        requested.append((PUBLISH, {}))
    if renewal_at and now >= renewal_at and now - last.get(RENEW, 0) >= 3600:
        requested.append((RENEW, {"renew_now": True, "activate_after_refresh": True}))
    for workflow, inputs in requested:
        if workflow in blocked or now - last.get(workflow, 0) < 60 or now < state.get("cooldown_until", {}).get(workflow, 0):
            continue
        # Record intent before transmission, so a timeout cannot cause blind replay.
        baseline = max((r["id"] for r in runs[workflow]), default=0)
        state["jobs"][workflow] = {"baseline": baseline, "requested_at": now, "signature": signature}
        state.setdefault("last_requested", {})[workflow] = now
        if workflow == SYNC:
            state["sync_results_needed"] = False
        write_state(path, state)
        dispatch(workflow, auth, inputs)
        print("Workflow dispatch accepted: " + workflow, flush=True)
    write_state(path, state)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/run/secrets/config.json")
    parser.add_argument("--state", default="/state/scheduler.json")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    while True:
        try:
            tick(config, Path(args.state), args.dry_run)
        except Exception:
            print("Scheduler check failed; sensitive details omitted. See local state and GitHub run status.", flush=True)
            if args.once:
                raise SystemExit(1)
        if args.once:
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
