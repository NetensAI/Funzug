# Runtime audit, 15 October 2026

All times below are IST. This audit does not establish full workflow readiness.

## Verified live state

- A fresh Chrome extension tab successfully opened Funzug's Meta Business Suite Planner. All 14 existing owner-approved image posts had corresponding Facebook and Instagram cards at the selected dates and times below. The two synthetic workflow tests were absent from the 16 October calendar, including their 8:00 PM and 8:15 PM slots.
- Five detail-page identifiers were independently rechecked against the main queue: Greenland shark Facebook `2087002212027665` and Instagram `3529415300551310`, fulgurite Facebook `4531045277163564` and Instagram `3339632156198634`, and NOAA Facebook `994721706985086`. Other rows below have live matching calendar cards; this audit did not independently reopen every detail identifier.
- A read-only BrandFlow database query confirmed the same 14 future image schedules, eight recorded published outcomes, and the two incomplete test checkpoints. No draft, approval, schedule or outcome record was changed.
- BrandFlow's public health endpoint reported `healthy`, database `connected`, timezone `Asia/Kolkata`.
- The Mini PC scheduler, BrandFlow database/dashboard and media host were healthy. The old native worker image `meta-selector-pr79-20261014` was unhealthy, with repeated test attempts and missing-card errors.
- Starting the Windows SSH agent restored its existing saved Funzug key. No key or publishing token was replaced. Changing the agent's startup mode to Automatic was denied by Windows; that does not stop the Mini PC's independent services.

| Image post | Selected IST slot | Live Planner cards |
| --- | --- | --- |
| Greenland shark | 17 October, 4:30 PM | Facebook and Instagram |
| Singing sand | 17 October, 8:18 PM | Facebook and Instagram |
| Fulgurite | 18 October, 12:30 PM | Facebook and Instagram |
| NOAA ocean carbon | 18 October, 4:30 PM | Facebook and Instagram |
| Ocean bioluminescence | 18 October, 8:17 PM | Facebook and Instagram |
| NASA SunRISE | 19 October, 8:18 AM | Facebook and Instagram |
| Octopus hearts | 19 October, 12:30 PM | Facebook and Instagram |
| Sea otters | 19 October, 4:30 PM | Facebook and Instagram |
| Havasupai mule mail | 19 October, 8:10 PM | Facebook and Instagram |
| Wood frog | 20 October, 8:13 AM | Facebook and Instagram |
| JBJ Soul Kitchen | 20 October, 12:30 PM | Facebook and Instagram |
| Chesapeake crossing | 20 October, 4:31 PM | Facebook and Instagram |
| Imagination Library | 20 October, 8:31 PM | Facebook and Instagram |
| Popcorn | 21 October, 8:33 AM | Facebook and Instagram |

## Mini PC Meta restriction and deployment

The dedicated browser rendered Instagram cards while Facebook cards remained empty loading spinners, even after scrolling and a bounded wait. A retained Facebook tab displayed **You're Temporarily Blocked**, explaining that the feature had been used too fast. This is evidence of a restriction in that browser session, not evidence that the saved Facebook schedules are missing. Do not switch browsers to submit around the restriction.

The replacement native worker runs image `funzug-native-worker:planner-audit-20261015`, image ID `sha256:ffe318c9862795063f155435e137731806753c85c403234a0c56ef592c4c8f70`. Its previous stopped container remains `funzug-native-worker-pre-audit-20261015` for rollback. Its state was backed up as `scheduler/native-state/native-worker.pre-planner-audit-20261015.json` before deployment. Existing private mounts and container restrictions were retained.

The worker is running with a persisted browser cooldown through **15 October at 4:44:38 PM**. Its health probe deliberately reports failure while a browser restriction remains unresolved. Its live active list contains exactly the 14 image posts, excluding both mixed-format tests. Acceptance and production mixed-format flags are off. The credential scheduler remains independent and running.

Changes in this deployment:

- A Meta block stops browser work across the entire queue for an hour, surviving restarts. Two consecutive browser timeouts also defer the queue instead of repeatedly hammering all approvals.
- Existing matching schedules are normally verified every six hours rather than every 15 minutes. Due publications and changed schedule/content bindings bypass this cache.
- Account selection uses the named `Post to` control, so captions containing “Funzug” cannot become a second account-selector candidate.
- The Planner reader waits for date/card/platform hydration, scrolls matching cards into view, refreshes column bounds after scrolling, waits for detail IDs and waits for dialogs to close.
- `python -m scheduler.audit_schedules` is a read-only receipt audit. It shares the worker lock, respects the cooldown, verifies reviewed image packages, and has no approval, upload or submission path.

The read-only Mini PC audit exposed the loading failures and did not pass. Do not report recovery until the worker independently observes matching receipts after the restriction clears. A configured cooldown or a running container is not recovery proof.

## Credentials and checks

- GitHub run [38354327182](https://github.com/NetensAI/Funzug/actions/runs/38354327182) completed the Instagram Login renewal successfully on 13 October at 11:30 AM. The next persisted renewal is 20 October at 11:31 AM. No early refresh was forced during this audit.
- Live GitHub environment variables were read as `FUNZUG_INSTAGRAM_API_MODE=instagram_login` and `FUNZUG_DELIVERY_MODE=meta_native`. Secret values were neither printed nor changed.
- Current-main CI [38708853144](https://github.com/NetensAI/Funzug/actions/runs/38708853144) succeeded. The local suite with these fixes passed 254 tests, with two FFmpeg-dependent tests skipped locally. Draft validation passed for 22 inbox items. Pending content was preserved and not fact-checked again.

## Remaining acceptance

1. Observe the native worker recovering from the Meta restriction and completing a full read-only receipt audit without retrying public submissions.
2. Finish actual scheduled-media verification and publication reconciliation for Carousel and Reel delivery. Both remain gated. The cancelled Reel identity must not be reused or re-enabled.
3. Complete a permitted mixed-format acceptance cycle, verify its actual platform media/order and slot, and reconcile cleanup. The current Carousel is only reserved; the cancelled Reel's old queue checkpoint is not delivery proof.
4. Continue quiet credential and service monitoring. A future revocation or required login is still an external owner-authentication event.

No social post was uploaded, approved, scheduled, rescheduled or published during this audit and fix deployment.
