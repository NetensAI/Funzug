# Funzug readiness, 13 October 2026

The end-to-end goal remains incomplete. Setup and credential access do not authorize publication. No posts were scheduled or published during the work recorded here.

## Verified

- PR #55 (`c9271b2`) merged the legacy Meta placeholder receipt reconciliation fix. It allows a verified schedule ID to replace a stored planner placeholder while retaining the other platform's unchanged placeholder during partial reconciliation.
- The merged BrandFlow helper is deployed at `/home/vatsal/apps/brandflow/lib/funzug-native-handoff.mjs`, SHA-256 `6d69bb579fe4f6adefff3d15ca8001ac5035ad68571360669d7ed96db234dce0`. The prior helper is preserved as `funzug-native-handoff.mjs.pre-pr55-20261013.bak`.
- BrandFlow dashboard and database containers are healthy. `/api/health` reports healthy, database connected, and timezone `Asia/Kolkata`.
- PR #55 checks passed: Python 132 passed, 1 skipped; BrandFlow Node 34 passed, 1 skipped. The deployed dashboard build compiled successfully.
- Instagram Login renewal run #2 completed successfully at 11:30 AM IST on 13 October. `FUNZUG_INSTAGRAM_API_MODE` is `instagram_login`.
- Mini PC scheduler is healthy. Last poll was 2:00 PM IST; no active workflows, error, or pending result sync. Next renewal is 11:31 AM IST on 20 October.
- Latest observed GitHub runs: renewal #2 success; BrandFlow draft approval sync #168 success; publish-approved #161 success; native Meta handoff #14 failed before PR #55 was merged and deployed.

## Native Meta reconciliation still required

The authoritative queue still has four approved posts:

- “This Flash Came From The Early Universe”: `submitting`, both platform receipts are legacy placeholders.
- “A World Between Star And Planet”: `scheduled`, both platform receipts are legacy placeholders.
- “Mars Wakes In Blue Light”: `submitting`, no platform receipts.
- “Could A Dead Star Grow New Worlds?”: `submitting`, no platform receipts.

BrandFlow currently reflects these incomplete checkpoints. A prior Meta Business Suite inspection found the first two posts published and the latter two scheduled, but the current Chrome and Edge browser connections report `User unavailable` with no accessible tabs. Do not treat old screenshots, queue state, a workflow run, or stored placeholders as current planner verification. Reopen the authenticated Meta Business Suite browser connection, inspect the live planner, then record only observed IDs and slots through the native handoff workflow. Do not repeat a schedule submission for an uncertain post.

There is no unattended native-browser scheduler. The native handoff currently uses an owner-approved queue reservation, a pre-submission checkpoint, one browser submission, planner inspection, and per-platform receipt reconciliation. Until the planner is accessible and these records are reconciled, do not tell the owner that all approvals are scheduled or ready for another approval batch.

## Remaining end-to-end work

1. Verify all four native Meta planner entries against the authoritative queue and BrandFlow, reconcile actual schedule or publication IDs, and verify the resulting audit records. Keep all times in IST. Do not alter existing Meta schedules.
2. Decide and implement the supported unattended handoff path after testing the authorized browser workflow. A reservation or Graph API publication alone does not prove that a post appears in the Meta Business Suite Planner.
3. Complete daily fresh-draft preparation with current source verification and on-image claim verification, source URLs, access dates, claim IDs, support notes, history/schedule checks, image review, and validator pass. Preserve pending drafts unchanged unless the owner directs otherwise.
4. Complete mixed-format review and publishing if still in scope. The existing pipeline has carousel publication code, but BrandFlow ingestion/review remains single-image. Reels are not implemented. Keep ordered assets bound to approved content before enabling multi-image approval.
5. Continue monitoring Instagram credential renewal. Renewal cannot prevent Meta revocation or required re-login after security or permission changes.

## Approval and safety invariants

- Approval is one confirmation plus the selected future IST slot. Reject remains available; no separate authorization typing is required.
- Approval binds the source claims, caption, platforms, MIME type, image bytes, and content hash. Schedule changes require explicit owner rescheduling and audit history.
- No public media upload or post publication before the owner approves the reviewed content and selected slot.
- Successful platform results are not replayed automatically. Partial failure preserves successful platform IDs and requires platform-specific reconciliation.
- Native Meta scheduling requires observed Business Suite planner receipts for every approved platform. A reservation, submission checkpoint, API response, or placeholder alone is not proof.
