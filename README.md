# Funzug publishing workflow

Workflow starter for Funzug's Facebook Page and linked Instagram Professional account.

Publishing uses Meta's Graph API. The queue is approval-gated, every factual claim needs a source, and images must be 1080x1350.

## Safety

- New queue items start as drafts.
- Items need a named approval before publishing.
- The default `publish-due` command is a dry run.
- Publishing also requires `--execute --confirm-publish FUNZUG`.
- Credentials are read from environment variables and never stored in the queue or audit log.
- Publishing attempts are recorded in `logs/events.jsonl`.

## Files

- `queue.json`: content, approvals, schedule, sources, and media URLs.
- `history.json`: inspected topics already visible in Meta, used to catch repeats.
- `meta_assets_snapshot.json`: Meta IDs and visible account details observed during setup.
- `config.example.json`: credential variable names and other settings.
- `funzug_pipeline.py`: validation, approvals, dry runs, and image publishing.

## Setup

1. In Meta Business Suite, confirm the Page and Instagram Professional account remain linked.
2. Create/configure a Meta app and obtain the access required for the intended use. Confirm current permissions and review requirements in Meta's documentation.
3. Set `FUNZUG_FACEBOOK_PAGE_ID`, `FUNZUG_FACEBOOK_PAGE_TOKEN`, `FUNZUG_INSTAGRAM_USER_ID`, and `FUNZUG_INSTAGRAM_ACCESS_TOKEN` in the scheduler environment. Set `FUNZUG_META_GRAPH_VERSION` if needed.
4. Add a draft to `queue.json` with a unique `topic_key`, public HTTPS media URL, 1080x1350 media, factual claims and checked sources, platforms, and an ISO-8601 scheduled time with timezone offset.
5. Review and validate it, then approve by name.
6. Run `publish-due` on a scheduler. A due time is interpreted from `scheduled_at`; this runner does not create a persistent scheduler.

## Commands

```text
python funzug_pipeline.py validate
python funzug_pipeline.py approve --id ITEM_ID --approved-by "Name"
python funzug_pipeline.py publish-due
python funzug_pipeline.py publish-due --execute --confirm-publish FUNZUG
```

Instagram uses a create-container then publish-container sequence. Facebook and Instagram are handled as separate operations. This starter currently publishes single images; carousel and Reel items are rejected pending their own media validation and upload flows.

## Meta setup notes

Facebook Page publishing and Instagram publishing are separate API operations. Instagram's container publishing requires an Instagram Professional account and a media URL accessible to Meta. Meta app review, account linkage, Page task access, current permissions, API version, and rate limits depend on the app and endpoint and should be confirmed before production use.
