# Funzug readiness, 13 October 2026

## Latest runtime audit, 15 October 2026

See [the current runtime audit](docs/runtime-audit-2026-10-15.md) before using the historical notes below. All 14 approved future image posts are visible on Facebook and Instagram in the live Planner at their selected IST slots, and BrandFlow records agree. SSH access was restored by starting the existing Windows agent. The dedicated Mini PC browser has a visible Meta temporary-block notice and stalled Facebook cards. The corrected worker is running with a persisted cooldown through 15 October at 4:44:38 PM IST; recovery has not yet been verified. Mixed-format delivery remains gated. The full goal is incomplete.

## Current deployment update

At the latest 13 October check, Mars completed native publication on both platforms at 6:26 PM IST. Successful workflow `38401439937` reconciled the published IDs with the original schedule receipts, and BrandFlow has its published timestamp. Hubble remains visible on both live planner entries for 14 October at 6:18 AM IST. This closes the previously open unattended publication-and-dashboard outcome gate for image posts.

PR #64 merged seven new individually generated, visually inspected, source-verified drafts. Sync run `38425276103` and validation run `38425276294` succeeded. A direct read of BrandFlow confirmed all seven new external IDs as `pending_review`, with no approval or published timestamp. Existing pending entries were preserved.

The ordered-media approval work adds a shared Python/JavaScript fingerprint contract for carousel order and reel metadata. It is preparation for mixed-format integration, not delivery support. The current native worker explicitly rejects non-image packages. Remaining mixed-format work includes database storage, authenticated asset previews, complete ordered-media review, approval-bound packages, upload preparation, native composer verification, per-platform receipt checks and publication reconciliation. A newly owner-approved image still needs a full automatic native submission acceptance test.

PRs #60 through #62 are also merged and deployed. Image `funzug-native-worker:pr62` reports healthy with no restarts. It polls future approvals and reconciles due native publications through the audited GitHub workflow. A read-only live test verified the publication reader against both SPHEREx platform posts. Published planner links are bound to exact caption, platform, date column and time. If Meta changes the post ID, the original schedule receipt is retained and the published outcome includes its scheduled ID and matching content fingerprint.

Acceptance evidence by requirement:

| Requirement | Evidence | Open acceptance gate |
| --- | --- | --- |
| Source verification | CONTENT_REQUIREMENTS.md; claim source IDs, support notes and source timestamps validated by funzug_pipeline.py | New daily batches still need actual primary-source inspection; metadata validation is not fact-checking. Preserve existing pending drafts unchanged. |
| Image handling | Native PNG/JPEG decoding, dimensions, rounding allowance and original-byte content hash checks; live composer test | Each new generated image still needs visual inspection and native 4:5 dimensions. No local resizing or cropping. |
| Owner approval | BrandFlow single confirmation, selected IST slot, named reviewer, content fingerprint and refreshed approval before submission | A newly owner-approved post must finish the deployed automatic handoff. No agent-created approval is permitted. |
| Meta scheduling | Live Mars and Hubble Facebook/Instagram planner matches; durable reserve, begin and submission-intent checkpoints | Newly approved submission still needs both actual live planner receipts. Existing schedules are not resubmitted as a test. |
| Logging and outcomes | Native workflow commits queue/history/events and syncs BrandFlow; live reader matches existing published SPHEREx posts | Observe one real due scheduled post completing unattended publication reconciliation and dashboard sync. |
| Credential readiness | Initial Instagram Login renewal succeeded; persistent browser session and GitHub App auth work; health monitoring active | Continue renewal monitoring. Security revocation or expired login may require owner authentication. |
| Mixed formats | API carousel implementation only | BrandFlow/native carousel and Reels review and delivery remain incomplete. |

The full goal is not complete. A healthy worker or green CI alone does not satisfy these open acceptance gates.

The notes below predate PRs #57 through #59. The persistent Mini PC native browser worker is now enabled, and `funzug-publish` selects `FUNZUG_DELIVERY_MODE=meta_native` for new approvals. New staged native approvals block due-time API publication before reservation. The live Mini PC adapter verified both upcoming Mars and Hubble posts against Facebook and Instagram planner IDs and approved IST slots. The active worker independently recorded both as scheduled without submitting either again. The earlier FRB and SPHEREx outcomes were reconciled through successful native workflows.

Composer preparation was live-tested using already-approved content, original image bytes, exact caption, both selected accounts and selected IST controls. No Schedule or Publish click occurred in that test. PR #60 adds stale-poll, actionable-error and checkpoint-stall health checks and current deployment notes. See `NATIVE_WORKER_IMPLEMENTATION.md` for deployment evidence.

Still unproven: a newly owner-approved item completing the automatic reservation, native submission and both live planner receipts; unattended post-publication outcome reconciliation; daily new-content preparation and mixed-format delivery. Existing pending drafts remain unchanged. Do not claim the entire goal is complete or treat the historical status below as current.

## Historical audit notes before native-worker deployment

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
