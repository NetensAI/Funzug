# Mini PC workflow trigger

This service polls BrandFlow's local authenticated review endpoint once a minute. It dispatches the existing GitHub approval sync workflow when an owner approval or reschedule changes. It dispatches the publisher when an approved post becomes due, then syncs completed publication results back into BrandFlow. The pipeline remains the authority for source, image, approval, and schedule validation.

The service never approves a draft, creates Meta media, or receives Meta tokens. It uses the Funzug GitHub App with an installation token narrowed to Actions write. The key is a read-only mount; only the selected Funzug repository is installed. No network ports are exposed. Logs omit credentials.

Dispatch intent is persisted before the API request. The service tracks the resulting GitHub run and refuses to blindly replay an ambiguous dispatch. Active workflows are respected, failed runs have a cooldown, and the publishing workflow never automatically retries a failed social post.

The renewal timer dispatches the credential workflow after the initial 25-hour token-age requirement and every seven days after a successful refresh. It persists timing across container restarts. All owner-facing schedule times use IST.

The native worker normally rechecks an unchanged future schedule every six hours. A changed content fingerprint or selected slot invalidates that interval, and due publication reconciliation is checked separately. A visible Meta temporary block, or two consecutive browser timeouts, persists an hour-long browser cooldown across restarts. Health remains failed until live verification succeeds. Existing schedules remain in Meta during the cooldown; new handoffs wait.

For a read-only existing-image receipt audit, stop the worker first and run `python -m scheduler.audit_schedules` inside its image with the same private mounts and browser network. The command shares the worker lock and respects the browser cooldown. It does not approve, upload or submit posts. Do not restart or bypass a cooldown merely to make the audit run.

Deploy under `~/apps/funzug-automation`. Install only the draft integration secret into `scheduler/secrets/config.json`, with mode 600. Mount the user-downloaded App key as `scheduler/secrets/github-app-key.pem`, also mode 600. Neither file belongs in Git.

Run the container once with `--once --dry-run` before starting it. Confirm one accepted sync workflow and its completed run, then verify the local scheduler state. A healthy container alone does not prove workflow completion.
Mixed-format package work: `verify_ordered_package` independently validates schedule identity, targets, content fingerprint and decoded ordered bytes. The native image now includes FFmpeg and the private validators. The live `advance` path still rejects mixed formats; do not enable the dashboard mixed-delivery flag until browser preparation, matching composer proof, planner receipts and publication reconciliation are implemented and verified. No worker deployment was performed for this change.

