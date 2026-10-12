# Isolated BrandFlow boundary tests

Run `npm ci --prefix brandflow/tests --ignore-scripts` and `npm test --prefix brandflow/tests` from the repository root.

The suite transpiles the repository's actual result handler and dashboard page, uses the real Zod schema and React server renderer, and replaces database/session/framework adapters with explicit fixtures. Unmocked application imports fail closed. It never connects to production, reads credentials, approves drafts, or invokes Meta.

Coverage includes authentication before database access, rejection of unapproved records, partial failures, immutable successful IDs, idempotent replay, audit rollback, and rendered failure guidance with rescheduling hidden. SQL transaction assertions verify handler intent with an in-memory adapter; they do not prove PostgreSQL durability, concurrent row locking, browser interactivity, or a live publishing round trip.
