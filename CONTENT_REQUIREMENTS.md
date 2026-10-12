# Funzug content requirements

When a reference image, screenshot, news story, viral claim, or accompanying text is provided, prepare both one new Funzug image and one ready-to-copy caption without asking which deliverable is wanted. Ask only if essential information is missing.

## Research and accuracy

- Fact-check current news, science, medicine, politics, law, statistics, viral claims, disputed history, and other uncertain claims before drafting.
- Prefer primary or authoritative sources. Do not repeat exaggerations from the reference. Omit unsupported names, dates, numbers, organizations, places, and conclusions.
- Keep politics and current affairs neutral. Distinguish animal from human studies, observational research from trials, prototypes from proven treatments, association from causation, preprints from peer-reviewed research, and lab results from real-world performance.
- Never invent quotes or attributions. Preserve puzzle and mystery answers unless explicitly requested.
- Store each factual claim with one or more source IDs and a concise `support_note` stating what the cited source establishes. Keep source URLs and notes in queue metadata, never in the public caption.
- Inspect the source content during research. Queue validation checks URL shape, timestamps, and claim-to-source references, but cannot determine whether a source is reachable, authoritative, current, or actually supports a claim. The named human reviewer must verify sources and claims before approval.

## Image

- For an image post, produce exactly one final image. For a carousel, produce 2-10 individual slide images, never a collage. Every image must be portrait 4:5 at exactly 1080x1350 pixels. Keep the main subject, headline, and Funzug branding inside safe margins.
- Make a fresh, premium, cinematic, high-contrast, mobile-first editorial design with one dominant cohesive scene. The source is for information and inspiration, not layout, typography, colors, branding, or composition to copy.
- Keep on-image text minimal: use one strong, curiosity-driven headline of about 5-10 words and at most one short supporting line. Do not place the whole story on the image.
- Every image must visibly include a small, tasteful `Funzug` wordmark, normally near the bottom. Do not include source-page logos or watermarks, fake quotes, fake statistics, or fake signage. Do not use cluttered collages or dense explainer panels.
- Keep people realistic unless a cartoon is requested. Maintain credible anatomy, animals, machinery, architecture, science, geography, and historical detail. Do not make speculative visuals appear to be documentary evidence.
- If using a real supplied photograph is essential, preserve it where possible and redesign the editable composition around it. Otherwise create a fresh visual.
- Inspect every final image and verify its actual pixel dimensions before adding it to the queue. Carousel `media_paths` and staged `public_media_urls` must use the same slide order.

## Caption

- Immediately provide a complete, natural, engaging, journalistic caption, usually 4-7 short paragraphs, with a strong opening, accurate explanation, helpful context, and why it matters.
- Use exactly one blank line between paragraphs. A few relevant emojis are fine. Avoid em dashes and semicolons when ordinary punctuation works.
- Finish with 4-6 relevant hashtags. Do not use `#Funzug`.
- Put only the public caption in a plain triple-backtick code block with no language label or attributes. Do not place IDs, sources, URLs, metadata, annotations, or tool details inside it. Put necessary caveats and source links outside the code block.

## Queue and approval

- Save generated images as project assets under `drafts/assets/`, include the verified `media_path`, and store each review-only post in `drafts/queue.json`. Run `python funzug_pipeline.py validate-drafts` before handing over the batch. Drafts may omit `public_media_url` and are not visible to the publisher.
- Only after a human reviews the content and every image is available at a public HTTPS URL, stage it with `python funzug_pipeline.py stage-draft --id ITEM_ID --public-media-url URL`. Repeat the flag once per carousel slide, in slide order. This copies it into `queue.json` as an unapproved draft. Every URL must be public, match the exact image, and contain no query string or embedded credentials.
- Create queue items as drafts. Never add an approval record on behalf of the user. The owner reviews sources, claims, caption, images, platform targets, and the selected IST schedule in BrandFlow. BrandFlow uses one confirmation checkbox and Approve or Reject. Clicking Approve authorizes public image hosting and publication at that selected time; no separate authorization phrase or six-checkbox screen is needed. The integration records the authenticated reviewer, review timestamp, review note, `publicationAuthorized`, and `approvalConfirmed`. Legacy CLI approvals with all six checklist flags remain supported.
- No workflow may publish without the item's explicit human approval, a non-empty review note, and a due schedule. The GitHub `funzug-publish` environment is restricted to `main`, but it does not add a separate reviewer gate.
