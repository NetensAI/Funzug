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
- `drafts/queue.json`: draft-only content and source evidence; public media URLs and approvals are not required.
- `drafts/assets/`: locally generated 1080x1350 draft images.
- `media-host/`: optional self-hosted Docker image origin with authenticated uploads and public read-only media URLs.
- `history.json`: inspected topics already visible in Meta, used to catch repeats.
- `meta_assets_snapshot.json`: Meta IDs and visible account details observed during setup.
- `config.example.json`: credential variable names and other settings.
- `funzug_pipeline.py`: validation, approvals, dry runs, and image publishing.


## Setup


1. In Meta Business Suite, confirm the Page and Instagram Professional account remain linked.
2. Keep the Meta app in Development mode for Funzug's own accounts, as requested. Only people with app roles can use permissions at Standard Access. Do not submit App Review or designate Funzug as a Tech Provider unless the owner later chooses to support accounts outside Funzug.
3. Add these secrets to the private GitHub repository under Settings > Secrets and variables > Actions: `FUNZUG_FACEBOOK_PAGE_ID`, `FUNZUG_FACEBOOK_PAGE_TOKEN`, `FUNZUG_INSTAGRAM_USER_ID`, and `FUNZUG_INSTAGRAM_ACCESS_TOKEN`. Set `FUNZUG_META_GRAPH_VERSION` as a repository variable if needed. Never commit tokens or paste them into chat.
4. The `funzug-publish` GitHub Actions environment is restricted to the `main` branch. This repository's environment settings do not expose a required-reviewer control, so per-post approval in the queue is the human publishing gate.
5. For each story, follow `CONTENT_REQUIREMENTS.md`. The ChatGPT/Codex built-in image generator can create the image within an interactive task using the ChatGPT plan. It is not callable by this GitHub Actions workflow. Do not put ChatGPT or Meta credentials in a prompt, queue item, image, or log.
6. Save locally reviewable posts and generated images in `drafts/queue.json` and `drafts/assets/`. Validate them with `python funzug_pipeline.py validate-drafts`. Drafts are not visible to the publishing workflow and do not need a public media URL.
7. After reviewing a draft, make its image available at a public HTTPS URL and use `stage-draft` to copy it into `queue.json`. The optional Docker media host in `media-host/` is prepared for a home server that is reachable over HTTPS; an authorized upload prints the public URL. Staging does not approve it. Researchers must inspect source content; URL syntax, metadata, or availability alone is not fact-checking.
8. Review the sources, caption, image, destinations, and scheduled time. Approve the item with a named reviewer and a non-empty review note only after it is ready to publish.
9. GitHub Actions checks approved posts every five minutes. Before any Meta publishing call, it verifies both tokens belong to the configured app, have the required scopes, and Meta explicitly reports both token expiry and data-access expiry as zero (non-expiring). A due item publishes only if its named approval record, review note, sources, media, and schedule all validate. Results are recorded in `queue.json`, `history.json`, and `logs/events.jsonl`. It does not generate or approve content, and it does not publish drafts.


## Commands


```text
python funzug_pipeline.py validate
python funzug_pipeline.py validate-drafts
python funzug_pipeline.py stage-draft --id ITEM_ID --public-media-url https://media.example.com/image.png
python funzug_pipeline.py approve --id ITEM_ID --approved-by "Name" --note "Reviewed sources, caption, image, platforms, and schedule"
python funzug_pipeline.py publish-due
python funzug_pipeline.py publish-due --execute --confirm-publish FUNZUG
python funzug_pipeline.py check-due
```


Instagram uses a create-container then publish-container sequence. Facebook and Instagram are handled as separate operations. This starter currently publishes single images; carousel and Reel items are rejected pending their own media validation and upload flows.


## Human approval and automation boundary


The scheduled runner can publish only items whose status and approval record both say `approved`, and only after `scheduled_at`. The approval record needs a reviewer name, a timezone-aware timestamp, and a non-empty review note. It performs a no-secret preflight first and only the publish job receives Meta credentials. The `funzug-publish` environment limits deployment to `main`; it does not provide a per-run reviewer control in this repository. A successful or failed item is not retried automatically, preventing accidental duplicate posts. Stories, sources, captions, and images are prepared in ChatGPT/Codex as drafts and reviewed before approval.


## Meta setup notes


Facebook Page publishing and Instagram publishing are separate API operations. Instagram's container publishing requires an Instagram Professional account and a media URL accessible to Meta. The app is intentionally kept in Development mode for Funzug's own accounts. Account roles, Page task access, token lifetime, and endpoint permissions still need periodic checks. Meta's official Instagram collection documents checking a media container's `status_code` and publishing it once processing is finished; the pipeline now waits for that ready state before calling `media_publish`.


The latest Meta Developers check found the `Funzug Publisher` app (ID `2180210799547573`) is unpublished and remains in Development mode by owner choice. Meta showed `instagram_content_publish` and `pages_manage_posts` as Ready for testing. No App Review submission or Tech Provider designation was made. Development mode is limited to app-role users, so confirm that the account operating the workflow has an app role and the necessary Page tasks. Current setup observations are recorded in `meta_assets_snapshot.json`.


Use the separate `Verify Meta credentials (read-only)` GitHub Actions workflow to check that the configured tokens can read the configured Page and Instagram account IDs. It never publishes. A passing check proves only object access, not content-publishing permission, app review, production readiness, or successful scheduling.


The latest read-only verification run [#14](https://github.com/NetensAI/Funzug/actions/runs/38060422447) confirmed read access to the configured Facebook Page and linked Instagram account before the latest token updates. It did not call a publishing endpoint. The verifier and publisher default to Graph API v26.0 when `FUNZUG_META_GRAPH_VERSION` is empty. This confirms object access only, not successful publishing or scheduling. The queue is empty, and no public posts have been made by this workflow.

The latest token diagnostic, [run #3](https://github.com/NetensAI/Funzug/actions/runs/38065854271), completed successfully after the token updates. It checked app match, validity, scopes, and expiry without logging token values. The displayed expiry was 2026-10-10 17:00 UTC, so the tokens were still valid at that run but close to expiration. Re-run the read-only diagnostic before relying on them; do not infer indefinite validity from a successful check. This diagnostic does not publish or prove an end-to-end post.


The privacy policy at `https://www.funzug.com/funzug-com-privacy-policy` was updated and published on 2026-10-10 with a Funzug Publisher App section covering app data use, storage, service providers, and retention. The user's personal email address was not included. This URL is now saved in the Meta app's Privacy Policy URL field. The app remains unpublished, and the remaining app details and publishing access still need verification.


Meta Business Suite already contains scheduled content through November 5, 2026. The visible recurring subjects are Valentina Tereshkova, Princess Leonor, El Niño, and Svalbard. These topic keys are present in `history.json`; check the live Business Suite schedule again before preparing new content. The listed times did not show a timezone.


## Codex-only workflow transition


The requested direction is to prepare content inside Codex using the ChatGPT image tool and a Codex scheduled task, not an external image-generation API. The Codex app has an active daily draft-preparation automation, named `Funzug daily draft preparation`, targeting 7 to 10 drafts per run. Its exact execution time and a successful unattended draft run have not been verified. The GitHub Actions file defines a five-minute publishing schedule, but scheduled polling has not been verified. The publishing queue has no approved items; the draft inbox contains one pilot item. Do not treat the system as Codex-only until the Codex run is tested, the Meta publishing path is verified, and the GitHub trigger is explicitly cut over.


The owner requested 7 to 10 posts per day. A scheduled Codex run should prepare drafts only. Each post still requires explicit owner approval before any Meta scheduling or publishing. Availability of image generation and the Chrome extension within unattended scheduled runs must be tested before relying on them.


GitHub lists the expected Facebook Page and Instagram token secret names in repository Actions secrets. The Meta app secret is stored in the `funzug-publish` environment and is not printed in workflow logs. Read-only diagnostic [run #4](https://github.com/NetensAI/Funzug/actions/runs/38073956546) confirmed that both saved tokens match the app and include all required scopes, but both have expired at 2026-10-10 17:00 UTC; their data-access expiry is 2027-01-08 15:46 UTC. The diagnostic fails closed, and the publishing workflow checks token validity before any publishing call. Replace both publishing tokens, then rerun the diagnostic and account-access verifier before considering credentials ready. The diagnostic did not publish or schedule anything.

The Cloudflare Tunnel `funzug-media` and public DNS/application route `media.funzug.com -> http://media:8080` are configured. The tunnel has no active connector yet. Finish the Linux Docker deployment using `media-host/README.md`, including securely placing the tunnel token on the server and setting the two GitHub Actions media-upload secrets. Public media uploads require an explicit human decision because the resulting image URL is accessible to Meta and the public.


## Image generation boundary


The built-in ChatGPT/Codex image tool uses ChatGPT plan usage in this conversation, but GitHub Actions cannot invoke that tool. OpenAI's current Sign in with ChatGPT plan-usage preview also does not support image generation. Therefore images must be generated in a ChatGPT/Codex task, saved into this repository, and reviewed before their queue item can pass validation. No API key or paid image API has been configured.
