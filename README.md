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
2. Create/configure a Meta app and grant only the permissions required for Page and Instagram content publishing. Confirm current permission and review requirements in Meta's documentation.
3. Add these secrets to the private GitHub repository under Settings > Secrets and variables > Actions: `FUNZUG_FACEBOOK_PAGE_ID`, `FUNZUG_FACEBOOK_PAGE_TOKEN`, `FUNZUG_INSTAGRAM_USER_ID`, and `FUNZUG_INSTAGRAM_ACCESS_TOKEN`. Set `FUNZUG_META_GRAPH_VERSION` as a repository variable if needed. Never commit tokens or paste them into chat.
4. Add a draft to `queue.json` with a unique `topic_key`, public HTTPS media URL, 1080x1350 media, factual claims and checked sources, platforms, and an ISO-8601 scheduled time with timezone offset.
5. Review the sources, caption, image, destinations, and scheduled time. Approve the item by name only after it is ready to publish.
6. The GitHub Actions workflow checks approved posts every five minutes and records each result in `queue.json`. It does not generate or approve content, and it does not publish drafts.

## Commands

```text
python funzug_pipeline.py validate
python funzug_pipeline.py approve --id ITEM_ID --approved-by "Name"
python funzug_pipeline.py publish-due
python funzug_pipeline.py publish-due --execute --confirm-publish FUNZUG
```

Instagram uses a create-container then publish-container sequence. Facebook and Instagram are handled as separate operations. This starter currently publishes single images; carousel and Reel items are rejected pending their own media validation and upload flows.

## Human approval and automation boundary

The scheduled runner can publish only items whose status and approval record both say `approved`, and only after `scheduled_at`. A person must review and approve each item first. GitHub Actions writes the resulting status back to `queue.json` so a successful post is not retried on the next run. The workflow does not research stories, generate images or captions, or approve posts. Those steps remain manual until a separate content-generation and review system is configured.

## Meta setup notes

Facebook Page publishing and Instagram publishing are separate API operations. Instagram's container publishing requires an Instagram Professional account and a media URL accessible to Meta. Meta app review, account linkage, Page task access, current permissions, API version, and rate limits depend on the app and endpoint and should be confirmed before production use.
