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
