# Native Meta scheduling

Implementation remains inactive until deployment and a live owner-approved handoff are verified. Do not reserve posts merely to test these steps.

## Deployment prerequisites

Apply BrandFlow migration 012 before deploying the changed reschedule route, native-handoff route and social-drafts page. Deploy the native handoff helpers and their type declarations together. Verify authenticated native checkpoint requests and reschedule rejection against the deployed dashboard. Keep the single owner approval confirmation and selected IST slot unchanged.

## Approved-post transfer protocol

1. Inspect the authoritative main queue, current BrandFlow approval and the live Funzug/funzugdotcom Meta planner. Do not transfer a post with any publication result, a changed content fingerprint, an expired slot or an existing matching native schedule without reconciliation.
2. Dispatch native-meta-handoff.yml with action reserve and the exact approved item ID. Wait for successful completion and inspect its committed main queue checkpoint. The workflow shares the publisher's queue-write lock and confirms the dashboard guard only after the repository checkpoint is pushed. A failure is not permission to continue.
3. Through the authorized browser extension, prepare the exact reviewed image and caption in Meta Business Suite. Confirm the selected Page and Instagram account. Verify the composer timezone and select the original approved IST instant on each target platform. Do not change approved content, add paid promotion, or schedule extra platforms.
4. Before clicking Meta's Schedule control, dispatch action begin. Wait for the committed submission checkpoint and successful BrandFlow confirmation. A repeated begin is intentionally rejected. If interrupted, inspect the planner instead of blindly clicking Schedule again.
5. Submit the prepared native schedule once, then inspect each platform's planner detail. Record the observed schedule identifier, exact IST slot, current observation timestamp and business.facebook.com planner URL. Save visual evidence without credentials. A toast alone is insufficient.
6. Dispatch action receipt separately for each observed platform using receipt_json with platform, schedule_id, scheduled_at, content_hash, planner_url and checked_at. Values must match the reserved main queue checkpoint. Wait for each completed workflow. The final state becomes scheduled only when every approved platform has a receipt.
7. Verify the committed queue and BrandFlow status. Meta owns delivery; never reactivate the due-time publisher for this item. Later reconcile actual publication identifiers and timestamps into the existing publication-result/audit integration. Receipt storage by itself is not proof of posting.

## Failure handling

An uncertain submission stays blocked. Do not remove native_handoff or change delivery_mode to recover automatically. First reconcile the native planner and platform-specific outcomes. Action dashboard can replay an already committed checkpoint to recover a failed dashboard sync without repeating a native submission. Existing unrelated owner schedules must not be edited or deleted.

There is no unattended browser runner yet. Merging these files does not automatically transfer future approvals to Meta or guarantee that a logged-out browser can schedule. Daily draft preparation, owner approval and credential renewal are separate from this transfer protocol.
