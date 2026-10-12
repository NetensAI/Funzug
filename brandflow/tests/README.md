# Isolated BrandFlow boundary tests

Run `npm ci --prefix brandflow/tests --ignore-scripts` and `npm test --prefix brandflow/tests` from the repository root.

The suite transpiles the repository's actual result handler and dashboard page, uses the real Zod schema and React server renderer, and replaces database/session/framework adapters with explicit fixtures. Unmocked application imports fail closed. It never connects to production, reads credentials, approves drafts, or invokes Meta.

Coverage includes authentication before database access, rejection of unapproved records, partial failures, immutable successful IDs, idempotent replay, audit rollback, and rendered failure guidance with rescheduling hidden. SQL transaction assertions verify handler intent with an in-memory adapter; they do not prove PostgreSQL durability, concurrent row locking, browser interactivity, or a live publishing round trip.

`postgres.test.mjs` additionally runs the actual outcome handler with a real PostgreSQL pool against a disposable local database named `funzug_test`. CI supplies this database as an isolated PostgreSQL 16 service and requires the suite to run. It verifies concurrent independent updates, conflicting IDs, real rollback after audit failure, rejection of unapproved records, and migration 010. The suite creates and removes only its random test schema. It rejects non-local hosts and any other database name. With no test URL, local runs explicitly skip this suite; skipped runs are not database evidence. Authentication/framework adapters remain fixtures. These tests do not prove interactive approval/rejection, rescheduling, or a live Meta publishing round trip.
