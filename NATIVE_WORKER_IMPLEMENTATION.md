# Native scheduling worker implementation status

Worktree: `codex/native-meta-worker`, based on main `241171f`.

Implemented locally, not deployed:

- A bearer-authenticated approved-media package endpoint. It reads only reviewed Funzug content, verifies approval, original image dimensions and the stored content hash, and returns no cacheable response. Pending, revoked, published and partially published items are rejected.
- A native scheduling controller with persistent reserve, begin and submission intent. A restarted or uncertain submission only inspects the planner. It never repeats the Schedule click. Receipt verification requires matching approved platforms, content fingerprint, IST slot and actual schedule IDs.
- The controller requires live planner inspection even for a saved scheduled checkpoint.
- A browser adapter now uses the observed account, upload, caption, date and time controls. It reads planner cards in the selected date column and obtains per-platform IDs from Post details. This adapter has compiled but has not been run in the Mini PC browser.
- A dispatcher correlates reserve, begin and receipt actions with unique GitHub workflow run titles, accepts only a completed successful run from the installed Funzug App, and persists intent before dispatch. The workflow accepts the correlation request ID.
- A separate Docker worker polls the private approved-media endpoint and runs the controller. Its default is disabled. Browser debugging is restricted to loopback inside the existing browser container's network namespace.

Verification on 13 October 2026:

- 21 controller, checkpoint dispatcher and worker selection tests passed.
- 21 BrandFlow boundary tests passed using unchanged dependencies from the existing checkout. No dependency installation occurred.
- Full Python discovery ran 143 tests, with 5 Windows temporary-directory cleanup permission errors and 1 skip. This is not a full-suite pass.
- The Meta composer was inspected through the authorized Edge extension. The selected accounts were Funzug and funzugdotcom. An already-approved Mars image and caption were tested in the composer and discarded without scheduling or publishing.
- Caption paste is verified by joining editor `[data-block]` textContent with newline separators. `innerText` introduces additional paragraph line breaks.
- Date input needs keyboard typing followed by Tab. Direct fill was ignored. Time spinbuttons need arrow keys and verification through `aria-valuenow` and `aria-valuetext`; direct fill was ignored.
- Media upload uses the Add photo/video file chooser. Successful upload shows one Remove photo button.

Remaining implementation:

1. Run the browser adapter against the persistent Mini PC browser, verify date-column and account checks, verify uploaded-image identity and render screenshots, and resolve selector differences. Never infer a receipt from a toast. Browser runtime remains unverified.
2. Deploy the private package route and correlation workflow first. Test the worker against that deployment. A checkpoint taking more than 45 seconds is left pending for reconciliation; it is not blindly repeated. Add automated continuation for long-running checkpoint jobs before unattended readiness.
3. Make native delivery the selected path for future BrandFlow approvals and prevent API due-time delivery before any browser submission. Preserve the existing API mode until a tested cutover, and clearly show which mode is active.
4. Build the new Docker image and enable the persistent Chromium loopback debugging listener while preserving its existing profile. Verify the configured browser timezone is IST. Do not expose its debugging endpoint publicly or copy session cookies.
5. Run CI, deploy and verify a newly owner-approved future post through both platforms. Existing approved posts already scheduled in Meta must only be reconciled.

Deployment has not occurred. An earlier dependency-install request was not executed because automatic approval review hit a usage limit. It was a review failure, not an unsafe-action determination. Existing installed dependencies were sufficient for the local boundary tests.
