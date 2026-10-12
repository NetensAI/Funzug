# Funzug readiness, 12 October 2026

Existing single-image drafts are available for owner review. The full goal remains incomplete. Setup permission does not authorize posting.

## Verified evidence

- Main checkpoint 6921ecd records the approved Orionids publication. PRs 36-45 are merged.
- Authenticated Chrome inspection showed seven pending cards with IST date/time selection, one unchecked confirmation, disabled Approve and enabled Reject. No controls were submitted. Pending-card times are proposals, not approved schedules.
- Daily workspace validation accepted eight retained inbox items. Structural validation is not renewed fact verification. Pending drafts remain unchanged at the owner's request.
- PR 42 and migration 011 accept positive portrait dimensions satisfying abs(width * 5 - height * 4) <= 2. 1080x1350 is preferred; native nearest-pixel 4:5 is allowed. No cropping or resizing. Retain Funzug headline and wordmark.
- All 120 local Python tests passed. PRs 44 and 45 passed mandatory PostgreSQL 16 CI tests covering actual review, outcome and reschedule transactions, competing reviews, audit rollback, slot history and platform-result guards. Auth/framework adapters remain fixtures.
- Owner-approved Orionids completed workflow run 38220155185 successfully. Facebook ID 124454514239741_1519437233554634 was recorded at 1:22:33 PM IST and Instagram ID 18116304065105811 at 1:22:49 PM IST on 12 October. BrandFlow persisted both results; Meta Business Suite independently displayed both posts. The approved slot was 1:20 PM IST, so this does not prove exact-minute delivery.
- Scheduler inspection at 12:57:53 PM IST found a healthy container, recent poll, no errors, no active workflows and no pending result sync. Renewal remains due 13 October 2026 at 11:30 AM IST, not proven complete.
- Read-only credential run 38213592972 passed current account-access checks, not future renewal or new publication.

## Pending implementation

PR 46 contains reschedule network recovery, explicit unknown publication timestamps and fail-closed native-handoff guards. Fifteen local boundary tests pass, including successful submission exactly once with the selected IST time. Merge and dashboard deployment remain pending. Edge access is restored. The linked Funzug Facebook and Instagram native composer exposes separate schedule controls, but no native schedule has been submitted.

The owner requested upcoming posts in Meta Business Suite. Native scheduling is not activated. Existing upcoming approvals remain workflow-managed. A manual reservation workflow now validates the existing BrandFlow approval, content fingerprint and unchanged future IST slot, then persists a blocking reservation under queue-write concurrency. This is not a native scheduling runner. Do not dispatch it until planner receipt reconciliation and the remaining dashboard integration are ready. An uncertain submission must remain blocked pending inspection, never be retried blindly. No automatic release or fallback is implemented.

## Remaining completion gates

1. Verify real renewal, encrypted replacement, diagnostics and publishing-mode activation. Renewal cannot prevent provider revocation or required re-login.
2. Complete native Meta scheduling integration and verify upcoming posts in the planner without duplicate publication. The existing single-image publication round trip is verified by the Orionids evidence above; inspect its audit entry separately.
3. Complete a fresh 7-10-post daily batch and review-only transfer. Verify new claims and image claims against primary/authoritative sources; retain access dates and claim support metadata. Check history and relevant live Meta schedule or report unavailable access. Do not re-verify existing pending drafts.
4. Complete mixed-format integration. Pipeline carousel publication exists, but BrandFlow sync rejects non-image drafts and ingestion stores one image. Reels are not implemented. Ordered assets must remain bound to reviewed content before carousel approval is supported.
5. Verify interactive native schedule submission and receipt reconciliation. Existing owner approval and live Meta publication are established for Orionids, not for native scheduling.

Owner controls remain one confirmation, future IST date/time and Approve/Reject. Approval authorizes only reviewed content and the chosen slot, including public media upload. No typed authorization or six-checkbox interface. Successful platform posts must not be replayed automatically.
