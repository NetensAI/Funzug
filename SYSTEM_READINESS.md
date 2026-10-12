# Funzug readiness, 12 October 2026

Status: **not ready for unrestricted owner approvals**. Do not mark the goal complete based on passing local tests or healthy containers.

## Current authoritative evidence

- Remote main is e09a535 (PR 35). The `codex/existing-result-route` branch has unmerged production result-route/identifier corrections, pending-draft revisions, exact-content approval checks, and updated instructions. GitHub Actions still executes main, not this branch.
- Dashboard source/build has the IST-only draft-ingest schema, per-platform outcome display, reschedule-outcome guard, and authenticated reviewed-content fingerprints. Database and container health passed after deployment.
- Private HTTPS transfer and read-only database inspection verified seven pending drafts, all unauthorized, with illustration disclosures and IST timezone. The already-reviewed record was unchanged. Orionids proposes 20 October at 7:30 PM IST; this is not an approved schedule.
- A read-only HTTPS comparison matched all seven pending draft fingerprints to local headline, caption, claims, sources, platforms, MIME type and exact image bytes. Cross-language canonicalization tests passed. Workflow enforcement still requires branch merge.
- All 111 Python tests passed. Eight outcome contract tests passed earlier. Production Next.js build/type checks passed. Pure tests do not prove live Meta publishing, unattended generation, or rendered partial-failure recovery.
- Scheduler inspection at 12 October 11:33 AM IST reported a recent poll, no active workflows, no recorded error and no pending result sync. Its last completed approval-sync workflow was 12 October 10:29 AM IST. The first refresh remains due 13 October at 11:30 AM IST. This is a live timer, not evidence of a completed token refresh.
- Existing saved inbox validation accepts eight exact1080x1350 images, including the already-published retained IceCube draft. Visual review is documented separately. Live Meta schedule has not been rechecked because Chrome extension returns User unavailable.

## Required remaining gates

1. Restore Chrome extension access. Create the fix-branch PR, inspect its checks, merge after passing, and verify main's workflow execution. Do not replace the PR/check workflow with an unreviewed direct main push.
2. Verify real Instagram refresh, encrypted credential replacement, full credential diagnostics and automatic publisher-mode switch after the minimum token age. Preserve failure-closed behavior. Normal renewal does not prevent revocation after security or permission changes.
3. Resolve native image-generation dimensions under the owner's generation-only constraint. Two built-in Mars attempts returned1122x1402 despite exact1080x1350 prompts. Neither was resized or queued. Do not silently weaken the dimension requirement or switch to a paid external API.
4. Replace the Mars queued artwork with a dimension-valid, clearly disclosed conceptual image; then transfer it only while pending review. Its current caption disclosure does not remove misleading on-image provenance wording.
5. Verify every claim and on-image factual statement against primary source content, including access dates and support notes. Structural validation cannot verify truth. Compare topic keys with current live schedule as well as saved history.
6. Complete an unattended daily run producing7–10 fresh, individually inspected dimension-valid images and captions, followed by review-only transfer. Existing files do not prove daily generation or transfer works unattended.
7. Exercise partial-platform failure rendering, reschedule rejection and safe recovery in a disposable integration environment. Never create invented failures in live approved drafts or automatically replay successful platforms.
8. Verify approval/rejection and scheduling end to end with owner-authorized content after the corrections are on main. No new live test post is authorized merely by this readiness audit.
9. Reconcile the original mixed image/carousel/reel content request with implemented capabilities: the publisher supports image/carousel formats, but BrandFlow draft integration currently accepts only one image; reels are not implemented. Do not claim the original format scope is complete.

The owner-facing interface remains one confirmation tick, selected IST date/time, and Approve/Reject. Approve authorizes only the reviewed content and chosen slot. No automation may infer approval from this document or an active goal.
