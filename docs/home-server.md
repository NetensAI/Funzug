# Funzug home execution

The home worker runs reservations, native scheduling, receipt persistence, publication reconciliation, daily credential verification and due weekly Instagram renewal. Its internal sequential scheduler polls once per minute; unchanged native schedules are checked every six hours. Already scheduled posts are delivered by Meta, not republished by a due-time Graph publisher. No recurring GitHub workflow dispatch is part of the home backend.

The restricted Phase 2 gate stages an exact source commit. Dry-run builds the home image, runs local executor tests in an offline container without production mounts, reads existing private runtime configuration inside the current worker, compares BrandFlow approved slots and native handoffs with the source queue, and verifies Instagram identity/permission without refreshing or posting. It saves a private report outside Git. Production cutover requires a fresh matching runtime-code digest, manual-only fenced workflows on current main, no browser restriction and no unsettled active submission intent.

## First-time setup and private state

Install the owner-reviewed restricted Phase 2 SSH extension once. It does not activate production. Stage a reviewed full commit SHA, run dry-run and examine its report. Only after dry-run passes remove GitHub production schedules and draft-path push execution, then stage that source revision and invoke cutover. The controller refuses deletion/recreation of an existing home container during initial activation.

The original scheduler credential mount stays read-only at /run/secrets. The owner-authorized one-time encrypted Actions artifact was decrypted inside the existing worker into scheduler/native-state/home-secrets.json, mode 0600, owned by the service user. It retains the current GitHub secret names, including FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL and FUNZUG_FACEBOOK_PAGE_TOKEN. No new .env credential store is required. No plaintext credential was committed, put in an image or printed. Renewed credentials remain local; manual GitHub failback requires securely synchronizing a newer bundle first.

The existing native-state directory is the persistent mounted volume. It holds native-worker.json, native-worker.lock, home-queue.json, home-history.json, home-jobs.json, execution-owner.json and private home-secrets.json. The local home queue and BrandFlow become the operational authorities after cutover. The repository queue is a historical bootstrap snapshot, not a live publication database. Atomic checkpoint writes fsync before the worker's Schedule click. Ambiguous submission intents are never cleared or replayed.

## Ownership and duplicate prevention

The repository Actions variable FUNZUG_EXECUTION_OWNER is the shared administrative fence. Every production GitHub job requires exactly github; home mutations require exactly home plus the private local marker. Missing/unknown ownership fails closed. Cutover first sets transition, drains old GitHub writers, stops the old scheduler/native worker and disables their restart policies, checks again for late writers, preserves state, then sets home and starts the one locked home worker. A local flock prevents concurrent home processes. The fence uses GitHub's API but does not execute Actions or consume runner minutes.

Never change the owner variable manually while another executor is running. The old containers remain stopped backups; no deletion or pruning is performed. Docker restart is unless-stopped for home, with a healthcheck and 10 MB x 3 JSON log rotation. The browser container and its authenticated profile are not replaced.

## Updates and logs

For a normal maintained checkout after quiescing the home worker and preserving its volume:

```sh
git pull && docker compose -f home-server/compose.yml up -d --build
docker compose -f home-server/compose.yml logs --tail=100 home-worker
```

Set the non-secret FUNZUG_DEPLOYMENT_ROOT environment variable to the existing deployment directory first. The restricted agent deployment uses immutable staged revisions rather than git pull in a detached release checkout. Do not use normal Compose recreation under a no-deletion instruction without owner approval; initial cutover deliberately refuses preexisting home-container replacement. Updates must retain the shared fence and volume and re-run dry-run before activation.

## Failure alerts

The healthcheck tests both native state and home job state. Failure events contain literal error codes only and are logged locally. An optional HTTPS webhook reads FUNZUG_FAILURE_WEBHOOK_URL from the private home-secrets.json store. It receives only service and code, at most once per hour for repeated failures. Email or Telegram can be connected to this pluggable webhook after the owner chooses a destination. No notification destination is configured automatically.

## Manual GitHub failback

Stop home and transfer ownership through the restricted rollback operation, never by concurrent dispatch. Automatic rollback is allowed only when the home queue still equals the source bootstrap snapshot and active intents are settled. Otherwise it refuses and requires an audited emergency export of the local queue/history/outcomes plus current renewal bundle before ownership changes. Keep home paused during that reconciliation. After github owns the fence, emergency workflow_dispatch is available; recurring schedules remain removed. Never replay an ambiguous submission or republish a recorded platform outcome.

The one-time encrypted transfer workflow remains manual only. CI on push/PR remains enabled and can still execute on GitHub. Zero recurring production Actions minutes does not mean zero CI/manual runner execution.
