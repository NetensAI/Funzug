# Funzug publishing workflow


Approval-gated publishing for Funzug's Facebook Page and Instagram account.


The deployed path uses BrandFlow approval and the persistent Mini PC browser to schedule posts in Meta Business Suite. The Graph API publisher remains available for separately configured workflow delivery, but is blocked for native-pending and native-reserved items. Every factual claim needs source evidence. Images must be native portrait 4:5, allowing nearest-pixel rounding; 1080x1350 is preferred, not mandatory. Do not resize or crop generated artwork.

## Current owner workflow

1. Open `https://funzug.netens.top` and review the pending post, image and factual evidence.
2. Select a future date and time in IST within the next 28 days, tick the single confirmation and click Approve. This authorizes only that reviewed content, selected platforms and selected time. Reject is available. No separate authorization phrase is needed.
3. The Mini PC worker transfers the approval through durable GitHub checkpoints, prepares the exact reviewed image and caption, schedules once and verifies each platform in Meta Planner. Leave at least 15 minutes before the selected slot for processing; slots too close to submission fail safely rather than publishing immediately.
4. Review the resulting Facebook and Instagram entries in the Meta Business Suite app. An approval or reservation is not proof of scheduling. Both live planner receipts must match the reviewed content and IST slot.
5. After the slot, the reconciliation worker reads explicit published evidence and synchronizes outcomes through the audited workflow to BrandFlow, `queue.json`, `history.json` and `logs/events.jsonl`. It never republishes to repair a missing result.

Deployment: Mini PC `funzug-native-worker:pr62`, with persistent state, health checks and `FUNZUG_DELIVERY_MODE=meta_native`. Both existing upcoming schedules were independently verified. Full acceptance is still pending a newly approved post completing the automatic handoff and a real scheduled-to-published transition completing audit synchronization. Mixed-format BrandFlow review is not yet supported. See `SYSTEM_READINESS.md` for remaining scope.

All publishing and proposed schedule times use India Standard Time (IST, `Asia/Kolkata`) only. Queue timestamps must include the `+05:30` offset; validation rejects other offsets before approval, public upload, or publishing. Dashboard schedule fields use `Asia/Kolkata`.


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
- `drafts/assets/`: locally generated portrait 4:5 draft images and carousel slides.
- `media-host/`: optional self-hosted Docker image origin with authenticated uploads and public read-only media URLs.
- `history.json`: inspected topics already visible in Meta, used to catch repeats.
- `meta_assets_snapshot.json`: Meta IDs and visible account details observed during setup.
- `config.example.json`: credential variable names and other settings.
- `funzug_pipeline.py`: validation, approvals, dry runs, and image/carousel publishing.


## Setup


1. In Meta Business Suite, confirm the Page and Instagram Professional account remain linked.
2. Keep the Meta app in Development mode for Funzug's own accounts, as requested. Only people with app roles can use permissions at Standard Access. Do not submit App Review or designate Funzug as a Tech Provider unless the owner later chooses to support accounts outside Funzug.
3. Add `FUNZUG_META_APP_SECRET`, `FUNZUG_FACEBOOK_PAGE_ID`, `FUNZUG_FACEBOOK_PAGE_TOKEN`, `FUNZUG_INSTAGRAM_USER_ID`, `FUNZUG_INSTAGRAM_ACCESS_TOKEN`, and `FUNZUG_MEDIA_UPLOAD_TOKEN` as secrets in the GitHub Actions `funzug-publish` environment. Set `FUNZUG_MEDIA_BASE_URL` to `https://media.funzug.com` as an environment variable. Never commit tokens or paste them into chat.
4. The default `FUNZUG_INSTAGRAM_API_MODE` is `facebook_login`, which uses the Facebook Graph API host for the linked Instagram account. The optional `instagram_login` mode uses Meta's separate Instagram Login API and `graph.instagram.com`; it does not require the Facebook Page link for Instagram publishing. It requires a token with `instagram_business_basic` and `instagram_business_content_publish`, plus an Instagram professional account ID. Set this repository variable only after configuring and verifying that separate login/token. The read-only diagnostic accepts tokens only while Meta reports them valid and both token and data-access expiry are either explicitly non-expiring or still in the future; it fails closed otherwise.
5. The `funzug-publish` GitHub Actions environment is restricted to the `main` branch. This repository's environment settings do not expose a required-reviewer control, so per-post approval in the queue is the human publishing gate.
6. For each story, follow `CONTENT_REQUIREMENTS.md`. The ChatGPT/Codex built-in image generator can create the image within an interactive task using the ChatGPT plan. It is not callable by this GitHub Actions workflow. Do not put ChatGPT or Meta credentials in a prompt, queue item, image, or log.
7. Save locally reviewable posts and generated images in `drafts/queue.json` and `drafts/assets/`. Validate them with `python funzug_pipeline.py validate-drafts`. Drafts are not visible to the publishing workflow and do not need a public media URL.
8. Review each draft's factual claims against its cited sources, inspect the source pages, caption, every image, platform destinations, and scheduled time. Source metadata or link availability alone is not fact-checking.
9. Use BrandFlow's single-confirmation approval screen and selected IST slot. The older GitHub manual approval command is an alternative interface, not the daily owner workflow. Never approve on the owner's behalf or upload unapproved assets.
10. Native delivery uses the authorized persistent Meta browser session and live planner verification. API delivery has a separate token preflight and remains blocked for native items. The Instagram Login credential-renewal workflow refreshes the API credential automatically; Meta security revocation or expired browser login can still require owner re-login. No setup can guarantee that Meta will never require authentication again.


## Commands


```text
python funzug_pipeline.py validate
python funzug_pipeline.py validate-drafts
python funzug_pipeline.py stage-draft --id ITEM_ID --public-media-url https://media.example.com/image.png
python funzug_pipeline.py stage-draft --id ITEM_ID --public-media-url https://media.example.com/slide-1.png --public-media-url https://media.example.com/slide-2.png
python funzug_pipeline.py host-and-approve-draft --id ITEM_ID --approved-by "Name" --note "Reviewed sources, image, caption, destinations, and schedule" --media-origin https://media.funzug.com --confirm-public-upload FUNZUG --authorize-publication "Yes, upload publicly and publish at scheduled time" --review-claims --review-sources --review-caption --review-images --review-platforms --review-schedule
python funzug_pipeline.py approve --id ITEM_ID --approved-by "Name" --note "Reviewed and verified all checklist items" --review-claims --review-sources --review-caption --review-images --review-platforms --review-schedule
python funzug_pipeline.py publish-due
python funzug_pipeline.py publish-due --execute --confirm-publish FUNZUG
python funzug_pipeline.py check-due
```


The API pipeline supports images and carousels. BrandFlow ingestion and the deployed native browser worker support single-image posts only. Do not interpret API carousel tests as end-to-end BrandFlow carousel readiness. Every image and slide must satisfy `abs(width * 5 - height * 4) <= 2` with positive portrait dimensions. Reels remain unsupported until video validation, review, approval binding and delivery are implemented.


## Human approval and automation boundary


The scheduled runner can publish only items whose status and approval record both say `approved`, and only after `scheduled_at`. The approval record needs a reviewer name, a timezone-aware timestamp, and a non-empty review note. It performs a no-secret preflight first and only the publish job receives Meta credentials. The `funzug-publish` environment limits deployment to `main`; it does not provide a per-run reviewer control in this repository. A successful or failed item is not retried automatically, preventing accidental duplicate posts. Stories, sources, captions, and images are prepared in ChatGPT/Codex as drafts and reviewed before approval.


## Meta setup notes


Facebook Page publishing and Instagram publishing are separate API operations. Instagram's container publishing requires an Instagram Professional account and a media URL accessible to Meta. The app is intentionally kept in Development mode for Funzug's own accounts. A Business System User token with the required publishing scopes is preferred for unattended use; choose the longest lifetime Meta permits, since Meta may still impose an expiry. Store credentials only in GitHub Actions secrets, never in chat. The same system-user token can be entered in both secrets if Meta grants both assets and scopes to it. The read-only preflight checks validity, app identity, permissions, and expiry before every publishing attempt. Finite-lived tokens are accepted only until either expiry passes, after which publishing fails closed and the token must be renewed. Meta's official Instagram collection documents checking a media container's `status_code` and publishing it once processing is finished; the pipeline now waits for that ready state before calling `media_publish`.

If Meta's Business Suite flow reports that Instagram login is needed, the optional `instagram_login` mode avoids using the linked Page to publish on Instagram. It uses a separate Instagram Login token and API host, and is subject to the same active-expiry checks. Facebook Page publishing remains on the Facebook Graph API. Do not enable this mode until the token diagnostic and read-only account check both pass for the new Instagram token.


The latest Meta Developers check found the `Funzug Publisher` app (ID `2180210799547573`) is unpublished and remains in Development mode by owner choice. Meta showed `instagram_content_publish` and `pages_manage_posts` as Ready for testing. No App Review submission or Tech Provider designation was made. Development mode is limited to app-role users, so confirm that the account operating the workflow has an app role and the necessary Page tasks. Current setup observations are recorded in `meta_assets_snapshot.json`.


Use the separate `Verify Meta credentials (read-only)` GitHub Actions workflow to check that the configured tokens can read the configured Page and Instagram account IDs. It never publishes. A passing check proves only object access, not content-publishing permission, app review, production readiness, or successful scheduling.


The latest read-only verification run [#21](https://github.com/NetensAI/Funzug/actions/runs/38078782078), on October 11, 2026, confirmed that both saved credentials can read the configured Facebook Page and linked Instagram account. It did not call a publishing endpoint. The verifier and publisher default to Graph API v26.0 when `FUNZUG_META_GRAPH_VERSION` is empty. This confirms object access only, not successful publishing or scheduling.

The latest read-only token diagnostic, [run #11](https://github.com/NetensAI/Funzug/actions/runs/38134827625), completed on October 11, 2026. It confirmed that both saved tokens are valid, match the Funzug app, and include their required scopes. Meta reports the Facebook token as non-expiring; the Instagram token expires December 9, 2026 at 12:09:30 UTC, with data access expiring January 8, 2027 at 19:08:09 UTC. The Instagram token is finite-lived. The diagnostic is read-only and does not prove a successful publishing call.

The latest scheduled publisher run, [run #8](https://github.com/NetensAI/Funzug/actions/runs/38126044277), completed on October 11, 2026. Queue validation found zero items and skipped the publishing job. No Meta publishing call was made. The five-minute schedule trigger is active.


The privacy policy at `https://www.funzug.com/funzug-com-privacy-policy` was updated and published on 2026-10-10 with a Funzug Publisher App section covering app data use, storage, service providers, and retention. The user's personal email address was not included. This URL is now saved in the Meta app's Privacy Policy URL field. The app remains unpublished, and the remaining app details and publishing access still need verification.


Meta Business Suite already contains scheduled content through November 5, 2026. The visible recurring subjects are Valentina Tereshkova, Princess Leonor, El Niño, and Svalbard. These topic keys are present in `history.json`; check the live Business Suite schedule again before preparing new content. The listed times did not show a timezone.


## Codex-only workflow transition

### BrandFlow review inbox

Funzug draft images and evidence are sent privately to the BrandFlow dashboard by the `Sync Funzug drafts with BrandFlow approvals` workflow. Configure `FUNZUG_DRAFT_INGEST_SECRET` as a secret in the `funzug-publish` GitHub Actions environment. Configure `FUNZUG_BRANDFLOW_DRAFTS_URL` as an environment variable, normally `https://funzug.netens.top/api/integrations/funzug/drafts`. The same random 32-byte secret must be set in BrandFlow's server-side `.env`. The workflow checks for explicit review authorization before it uploads an image to the public media host or places a post in the approved publishing queue.

The workflow runs every five minutes and can also be dispatched manually. Before enabling it, deploy the BrandFlow migration and API changes documented in its project. It does not call Meta itself. The existing publisher sends only approved queue items after their scheduled time. Never put the ingest secret in the repository, draft queue, or workflow logs.


The requested direction is to prepare content inside Codex using the ChatGPT image tool and a Codex scheduled task, not an external image-generation API. The Codex app has an active daily draft-preparation automation, named `Funzug daily draft preparation`, targeting 7 to 10 drafts per run. Its exact execution time and a successful unattended draft run have not been verified. GitHub's five-minute publishing schedule has run successfully, but the publishing queue currently has no approved items and the scheduled publisher has not made a Meta publishing call. The live BrandFlow review inbox showed eight `pending_review` drafts on October 11, 2026, with every review checkbox clear. Do not treat the system as Codex-only until the Codex run is tested, the Meta publishing path is verified, and the GitHub trigger is explicitly cut over.


The owner requested 7 to 10 posts per day. A scheduled Codex run should prepare drafts only. Each post still requires explicit owner approval before any Meta scheduling or publishing. Availability of image generation and the Chrome extension within unattended scheduled runs must be tested before relying on them.


The current credentials passed the read-only token diagnostic on October 11, 2026. The Instagram token will need renewal before December 9, 2026 unless replaced with a longer-lived token configured for the Funzug app, assigned assets, and required publishing scopes. Neither the diagnostic nor account-access verifier publishes or schedules anything. The open Instagram Login refresh proposal applies only if `FUNZUG_INSTAGRAM_API_MODE` is changed to `instagram_login`; the current default is `facebook_login`.

The Cloudflare Tunnel `funzug-media` and route `media.funzug.com -> http://media:8080` are configured. On October 11, 2026, read-only checks found the Mini PC's `media-host-media` and `media-host-cloudflared` containers running, and `https://media.funzug.com/health` returned HTTP 200. This verifies service reachability only, not an authenticated upload. Public media uploads require an explicit human decision because the resulting image URL is accessible to Meta and the public.


## Image generation boundary


The built-in ChatGPT/Codex image tool uses ChatGPT plan usage in this conversation, but GitHub Actions cannot invoke that tool. OpenAI's current Sign in with ChatGPT plan-usage preview also does not support image generation. Therefore images must be generated in a ChatGPT/Codex task, saved into this repository, and reviewed before their queue item can pass validation. No API key or paid image API has been configured.
