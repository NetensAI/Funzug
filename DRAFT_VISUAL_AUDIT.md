# Saved draft visual audit

Inspected all eight final PNG files individually on 12 October 2026. `validate-drafts` passed for all eight, including exactly 1080x1350 pixels. This is an editorial inspection, not owner approval. No images, captions, approval records, schedules, or live posts were changed.

All eight have visible Funzug wordmarks, legible headlines, one cohesive composition, and no visible source-page logos. The wordmark typography varies between assets; it is not a consistent locked brand mark. None contains people requiring facial-consistency review.

| Draft | Observed issue or disposition |
| --- | --- |
| IceCube | Branded conceptual cutaway, not a documentary detector photograph. Already appears in publication history. Do not approve the retained draft as a new post. |
| FRB | Branded conceptual cosmic scene. The beam and rings are illustrative, not an observed visible-light image of a radio burst. Requires illustration disclosure. |
| Brown dwarf | Branded conceptual atmospheric world. Do not imply this is a resolved SPHEREx photograph. Requires illustration disclosure. |
| Curiosity dawn | Branded synthetic rover landscape with an Earth-like orange sunrise. The phrase “Curiosity captured a rare dawn” beside synthetic artwork risks implying the artwork is the actual captured photograph. Hold for artwork revision or prominent illustration disclosure and factual visual review. |
| Hubble candidate | Question-form headline retains uncertainty, but the artwork depicts a solid world. Requires clear conceptual-illustration disclosure so a candidate interpretation is not presented as an observed confirmed planet. |
| Orionids | Branded conceptual meteor scene. On-image text says October 21–22; the proposal is November 8. Caption also says “this month.” Hold until the owner selects an appropriate future slot and the caption/image are reviewed together, or replace both with evergreen versions. |
| NOAA ocean carbon | Branded research-vessel concept. Glowing data lines on the ocean are illustrative, not visible measured carbon. Requires illustration disclosure. |
| SunRISE | Six spacecraft are visible, consistent with the headline count. Geometry and scale are conceptual. Requires illustration disclosure and mission-configuration review. |

## Remaining gates

Local draft correction: all seven unpublished captions now identify their artwork as AI-generated illustrations. The Orionids proposal is now 20 October 2026 at 7:30 PM IST, before the peak. This is a review proposal, not a publishing schedule. These edits have not yet been transferred to BrandFlow. The Mars image still warrants revision despite caption disclosure because its on-image wording can imply documentary provenance.

Use `python scripts/brandflow_sync.py sync --update-pending` for explicitly requested draft corrections. This opt-in operation updates only rows reported as pending_review, unauthorized, and unpublished. The server rechecks pending status during its upsert, so a concurrent owner approval prevents an overwrite. The ordinary sync continues to skip existing rows. Never use a new ID to bypass an approved-content conflict.

- Do not mark any held draft approved through this audit.
- Correct pending-draft artwork/captions as needed, then revalidate and sync through the review-only path. Any changed approved content must require renewed owner approval.
- Compare current source material against every caption and on-image factual statement. This inspection does not independently verify all science claims.
- Inspect the live Meta schedule when Chrome extension access is available. Saved `history.json` alone is not current schedule evidence.
- Test unattended daily preparation and review-only transfer. Existing saved artwork does not prove that automation works.
