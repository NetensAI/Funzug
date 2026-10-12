# Workflow readiness audit

Evidence checked on 12 October 2026. This document does not approve any post and is not a declaration of full readiness.

## Owner workflow

Open https://funzug.netens.top, review a pending draft and its evidence, select the date and time in IST, tick the single confirmation, then click Approve. Reject leaves it unpublished. Approval authorizes public media upload and scheduled publication. No separate authorization phrase is required in BrandFlow. The legacy GitHub/CLI approval interface remains available but is not the normal owner workflow.

The Mini PC checks local BrandFlow approvals once a minute. Approval or reschedule changes dispatch the existing approval-sync workflow. A due approved post dispatches the publisher. Completed workflow results sync back into BrandFlow. Dispatch tracking prevents blindly replaying ambiguous requests. Failed social posts are not automatically retried.

## Verified evidence

- Main includes PRs #30, #31, and #32. PR #32 passed both GitHub checks; the local suite passed 98 tests before submission.
- The Mini PC scheduler was rebuilt from PR #32 and reports healthy. Its non-secret state records a successful local poll and no outstanding jobs. Key and configuration files have mode 600.
- Mini PC-triggered approval sync completed successfully: https://github.com/NetensAI/Funzug/actions/runs/38205964870.
- Eight saved draft items pass `python funzug_pipeline.py validate-drafts`. This checks structure and media requirements, not factual support or visual quality.
- The replacement Instagram Login credential passed account identity and content-publishing quota checks and was saved encrypted in GitHub: https://github.com/NetensAI/Funzug/actions/runs/38205440521.
- The private GitHub App is installed only on NetensAI/Funzug. Runtime installation tokens are generated automatically and narrowed by operation. Its signing key is privately mounted, not committed.

## Remaining completion gates

1. The first real Instagram refresh must succeed after the minimum token age. The Mini PC timer is set for 13 October 2026 at 11:30 AM IST. Only after saving the refreshed bundle and passing both platform checks does it enable Instagram Login publishing. Until that succeeds, the existing publishing mode remains active. A bootstrap success is not a renewal success.
2. Verify the refreshed credential through the publisher's live read-only preflight. Never publish a test post without owner authorization.
3. Verify unattended daily preparation of 7 to 10 fresh drafts using the built-in image tool, authoritative source inspection, history and live Meta schedule checks, individual 1080x1350 images, visual inspection, and draft validation. A configured automation or a structurally valid old batch does not prove a successful daily run.
4. Inspect the pending batch's source support and images against CONTENT_REQUIREMENTS.md before claiming it is ready for owner review. Do not claim the live Meta schedule was checked when browser access is unavailable.
5. Confirm owner-visible failure status and final publication results for both platforms. Retain per-platform results and never retry a successful platform when recovering the other.

## Credential boundary

Routine Instagram expiry is handled by the renewal workflow, not repeated manual secret replacement. Weekly successful renewals extend its lifetime. Meta revocation, account security changes, lost app access, or a prolonged server outage can still require reconnection. Never promise that credentials cannot be revoked. Renewal failures must be reported before expiry; publishing fails closed on invalid or expired credentials.

The daily draft automation cannot approve, upload public media, schedule, publish, or access credentials. Research URLs, access dates, claim source IDs, and support notes belong in metadata, not captions. Files under the project `sources/` directory remain read-only.
