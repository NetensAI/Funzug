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

The image composer's Schedule controls must not be assumed to exist in this
wizard. Edit, Share, video processing, scheduling, and final planner verification
still require observation with explicitly authorized content. Mixed delivery
and mixed approval remain disabled until those stages are implemented and tested.
