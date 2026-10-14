# Native mixed-media controls

Observed on 13 October 2026 using the connected Chrome extension for Funzug
and funzugdotcom. Inspection did not upload media, save drafts, or schedule.

## Carousel entry

The Planner's `Create post` button opens the shared image composer. Its Media
description states that Instagram posts cannot exceed ten photos.
`Add photo/video` opens a file chooser directly. Post-upload thumbnail order
and count have not yet been observed, so this is not delivery proof.

On 14 October, the owner authorized an unsaved upload test. Sequential uploads
of the wood-frog and singing-sand originals produced two `Remove photo` controls
in that order. Both displayed 1122 x 1402. The single-image `Edit photo` label
changed to `Edit photos`. Each Remove control's fourth ancestor contained one
thumbnail image with an empty alt attribute and a distinct Meta CDN URL. The
visible screenshot confirmed frog first and dunes second. The Facebook preview
is a side-by-side layout, not evidence of Instagram carousel behavior. No caption,
schedule, Finish later, or Publish action was submitted. The unsaved composer is
retained for continued testing. CDN identity/order can be captured after each
sequential upload and checked again before submission; a count alone is insufficient.

## Reel entry

Planner toolbar `Create` opens a menu with `Create reel`. This opens a separate
`Create reel` wizard with Create, Edit, and Share stages. Edit and Share are
disabled initially. The account combobox reads `Post to Funzug and funzugdotcom`.
`Add Video` is enabled; `Add Photos` is disabled. The caption is a textbox named
`Write into the dialogue box to include text with your post.`
`Next` is disabled until media is present. `Cancel` is available.

On 14 October the authorized unsaved synthetic MP4 test displayed its filename
and actual 320 x 400 dimensions. Processing exposes suggested thumbnails and a
copyright check. The bottom Next differs from the thumbnail strip's Next.
Edit shows Audio, Crop, Text and Optimizations. Advancing without edits reaches
Share. Its Scheduling options contains Share now (initially pressed), Schedule
and disabled Save as draft. The separate final action initially says Share.

Selecting the scheduling option (not submitting) displays independent Facebook
and Instagram fields. Each date textbox is named
`Select a future date and time to publish your reel at. Date picker`; time
spinbuttons are hours, minutes and meridiem. Both show Asia/Kolkata.
Scheduling changes the Edit stage to skipped, so the adapter must not assume the
Edit-stage state persists. Optional switches include Add to playlist, Share to
Facebook Story, Add a poll and Tracking. Auto-generated closed captions are on;
translated audio and Meta AI voice translation are off. These options need
explicit reviewed policy rather than silently changing the original video.

No final Share, Schedule, or Save as draft action was clicked. The final schedule
button, video identity verification, and resulting planner details still require
implementation and verification. Mixed delivery and approval remain disabled.

Follow-up inspection of the retained Share-stage test found no HTML video
elements. The preview still reported `Reels · Loading...`, despite the copyright
check succeeding. Therefore HTML videoWidth, videoHeight, duration, and currentSrc
cannot yet be used as acceptance proof for this fixture. Do not infer a playable
or identity-verified video from the upload filename, dimensions, or copyright
message. Test a conventional non-fragmented MP4 fixture and inspect the visible
preview again before implementing final Reel preparation proof.

The conventional replacement fixture (H.264/yuv420p plus AAC, faststart, five
seconds, 720 x 900) reached 100% upload and displayed `Reels · 5 seconds`, rather
than Loading. Its blue suggested thumbnails were visible and copyright checks
passed. The preview rendered through canvas: there were two canvas elements, no
iframe, and no HTML video element. A screenshot showed the preview surface black
at that instant, so this is not proof of successful visual playback. Duration
readback must use the visible preview label, not nonexistent HTML video metadata.
The first synthetic test was discarded without saving. The replacement remains
unsaved for further inspection; no final submission was performed.

The conventional test's Share stage has two Schedule buttons after selecting
scheduling. The option has aria-pressed=true; the final submission button has no
aria-pressed attribute. The Share-stage accessibility snapshot did not expose
the test caption even though it was entered into Create. Final proof must read
the Create caption afresh and then verify the preserved Share scheduling fields;
stored Python caption data alone must not stand in for a live read.

Live round-trip verification confirmed that Share Back returns to Create when
Edit is skipped. The caption editor is a DIV with contenteditable=true and
data-block children, not an input. Reading its value/input_value is incorrect.
The test caption remained intact. The bottom Next returned directly to Share;
both date inputs and all time spinbutton values were preserved unchanged.

Both isolated acceptance drafts passed draft validation and schema-v2 payload
decoding in the Mini PC FFmpeg/Pillow container, with networking disabled and
the staging directory mounted read-only. The fixture inbox remains unapproved.
Verified ordered content hashes are:

- Carousel: 03f4fbfbb65f1df0c5c0485391110ed05947d0d7378a74405065819dae46b8ff
- Reel: 55c1d20d240846903058ff2a7c27f31f2dfa583ce8b5f732063cfa06f13199c7

The container must run as the staging owner (UID/GID 1000), rather than the
dashboard image's app user. No production file permissions were changed.

The hash-bound approval screen and review route passed a complete isolated
Next.js 14.2.35 production build, including TypeScript checking and all 27 static
page generation steps. Image tag: brandflow-pr67-check:review-hash. Image manifest
list: sha256:69a336577fc2431082de4af24573667037f5907ebb4bb170819d9f9743f1f89a.
This staging build did not restart production or apply database migrations.

On 14 October, CI runs 38519004965 and 38519001232 completed successfully.
Production migrations 013 and 014 were then applied in one PostgreSQL transaction
after verifying a private custom-format backup at
`/home/vatsal/apps/brandflow/.backups/pre-pr67-20261014-ordered-media.dump`.
Backup permissions are 0600; directory permissions are 0700. The archive is
35,815,035 bytes and passed pg_restore --list validation. The new ordered-media
table exists and all 15 existing draft records remain format=image. No approval,
schedule, publication, dashboard restart, or mixed-delivery activation occurred.

PR #67 merged as 9aaf5d319a7fcfdfdc19bf11e0ab13539a284ddc after both checks passed.
The verified review-hash dashboard image was then deployed with Compose
--no-deps --no-build, replacing only the dashboard. Previous image
sha256:854d7b744658a42f71fa319d58133c418290182b8d5bb359f2bdcd87a67236b0 is retained
as brandflow-dashboard:pre-pr67-20261014. Mixed delivery was not enabled.
The deployment initially reported running/health-starting; verify health before
reporting operational readiness. Production source promotion is still pending,
so do not rebuild the dashboard from its old source directory yet.

Source promotion is now complete: 30 scoped files plus the mapped social-drafts
page were copied after private backups. Credentials and unrelated application
source were excluded. The production page matches the tested staging page at
SHA-256 5f8d30a2edb1adcb4c00e3ff222d3db3fe1a6f0814bdaeaa5e7aaf19ec52635a.
Docker now reports the dashboard running and healthy. Mixed delivery remains off.
