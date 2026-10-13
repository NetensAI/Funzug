# Owner-requested pending draft revision

The owner requested captions without the AI-generation paragraph, no visible AI illustration mark, different Funzug lettering on every image, and a very small brand signature. Nine pending-review images were edited with the built-in ChatGPT image tool. Earlier oversized or fixed-logo variants were rejected and are not referenced by the queue. Original assets are retained.

Accepted assets are the nine `drafts/assets/*-small-brand.png` files referenced by the draft queue. Each final image was individually inspected for headline accuracy, scene preservation, small legible branding, and absence of an AI label. Pixel dimensions were checked without resizing or cropping. Claims, source metadata, headlines, platforms and proposed IST slots remain unchanged.

## Final prompt set

Each original image was the edit target. Common prompt: remove only any AI illustration text; replace the plain Funzug text with a small, discreet custom wordmark reading exactly `Funzug`, approximately 12% of canvas width and no more than 3% of its height, near the bottom with safe margins. Preserve all headline/supporting words, scene composition, anatomy, subjects, colors, lighting and framing. Add no scene elements or replacement disclosure. Output one native 4:5 portrait image, with nearest-pixel rounding allowed, never a collage. No local cropping or resizing.

Distinct brand treatments:

- Glassfrog: botanical emerald-and-ivory leaf-vein calligraphy.
- Wood frog: icy silver crystalline serif.
- Greenland shark: arctic silver-blue engraved lettering.
- Brine pools: pearl-white fluid ripple lettering.
- Octopus: copper-cream curling calligraphy.
- Singing sand: warm sandstone dune-contour lettering.
- Fulgurite: amber-ivory angular glass lettering.
- Ocean carbon: azure-white nautical wave lettering.
- SunRISE: gold-ivory orbital futuristic lettering.

Only caption disclosure paragraphs were removed from the review-only inbox. Scientific caveats such as candidate status, future mission status, scale, and illustrative data lines remain where relevant. Historical publisher queue, platform posts and original approval records were not rewritten by this revision.

`refresh-pending-drafts.yml` runs validation and `sync --update-pending` only. It has no public upload credential, no approval processing and no publishing step. The receiver rejects any item that is no longer pending review. A successful refresh still requires a read-back comparison of the dashboard content fingerprints before reporting the queue ready.
