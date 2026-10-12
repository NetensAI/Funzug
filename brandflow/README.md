# Additive BrandFlow outcome reporting

This directory versions the dashboard changes required by `scripts/brandflow_sync.py sync-results`. Deploy the server endpoint and migration before merging the client change. The old completed-only publications endpoint remains untouched.

Map `app/`, `lib/`, and `db/` to the corresponding BrandFlow server directories. Map `social-drafts-page.tsx` to `app/social-drafts/page.tsx` and `middleware.ts` to the server root. The exact outcomes route uses its own mandatory bearer authentication, like the existing integration endpoints. Preserve the server's `.env`, existing source, and database. Apply migration 009, build the dashboard, and restart only the dashboard service. Verify unauthorized requests are rejected and authenticated result updates are idempotent before switching the GitHub client.

The new endpoint accepts only results for an already-approved Funzug draft, never approval instructions. It records individual published/failed results and a full-publication timestamp only when every selected platform succeeded. Successful platform records cannot be erased or replaced with a different post ID. Raw failure messages are neither transmitted nor stored. The UI hides rescheduling once an outcome exists; this is not a new retry mechanism.

Run `node --test brandflow/tests/funzug-outcomes.test.mjs` from the Funzug repository. Pure contract tests do not replace a dashboard build, authentication checks, or database integration tests. Deployment and live verification are still required.
