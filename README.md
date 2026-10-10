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
4. The `funzug-publish` GitHub Actions environment is restricted to the `main` branch. This repository's environment settings do not expose a required-reviewer control, so per-post approval in the queue is the human publishing gate.
5. For each story, follow `CONTENT_REQUIREMENTS.md`. The ChatGPT/Codex built-in image generator can create the image within an interactive task using the ChatGPT plan. It is not callable by this GitHub Actions workflow. Do not put ChatGPT or Meta credentials in a prompt, queue item, image, or log.
6. Add a draft to `queue.json` with a unique `topic_key`, exact 1080x1350 `media_path`, matching public HTTPS `public_media_url` without query strings, fact-checked claims and source records, platforms, and an ISO-8601 scheduled time with timezone offset.
7. Review the sources, caption, image, destinations, and scheduled time. Approve the item with a named reviewer and a non-empty review note only after it is ready to publish.
8. GitHub Actions checks approved posts every five minutes. A due item publishes only if its named approval record, review note, sources, media, and schedule all validate. Results are recorded in `queue.json`, `history.json`, and `logs/events.jsonl`. It does not generate or approve content, and it does not publish drafts.

## Commands

```text
python funzug_pipeline.py validate
python funzug_pipeline.py approve --id ITEM_ID --approved-by "Name" --note "Reviewed sources, caption, image, platforms, and schedule"
python funzug_pipeline.py publish-due
python funzug_pipeline.py publish-due --execute --confirm-publish FUNZUG
python funzug_pipeline.py check-due
```

Instagram uses a create-container then publish-container sequence. Facebook and Instagram are handled as separate operations. This starter currently publishes single images; carousel and Reel items are rejected pending their own media validation and upload flows.

## Human approval and automation boundary

The scheduled runner can publish only items whose status and approval record both say `approved`, and only after `scheduled_at`. The approval record needs a reviewer name, a timezone-aware timestamp, and a non-empty review note. It performs a no-secret preflight first and only the publish job receives Meta credentials. The `funzug-publish` environment limits deployment to `main`; it does not provide a per-run reviewer control in this repository. A successful or failed item is not retried automatically, preventing accidental duplicate posts. Stories, sources, captions, and images are prepared in ChatGPT/Codex as drafts and reviewed before approval.

## Meta setup notes

Facebook Page publishing and Instagram publishing are separate API operations. Instagram's container publishing requires an Instagram Professional account and a media URL accessible to Meta. Meta app review, account linkage, Page task access, current permissions, API version, token lifetime, and rate limits depend on the app and endpoint and should be confirmed before production use. The connected app is currently in development/testing, so the stored token is not proof of production readiness.

## Image generation boundary

The built-in ChatGPT/Codex image tool uses ChatGPT plan usage in this conversation, but GitHub Actions cannot invoke that tool. OpenAI's current Sign in with ChatGPT plan-usage preview also does not support image generation. Therefore images must be generated in a ChatGPT/Codex task, saved into this repository, and reviewed before their queue item can pass validation. No API key or paid image API has been configured.
