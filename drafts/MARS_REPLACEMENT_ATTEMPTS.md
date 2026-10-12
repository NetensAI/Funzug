# Mars replacement attempts

Built-in image-generation tool only. Owner retained Funzug headlines/wordmark and declined local resizing or cropping on 12 October 2026. Neither candidate is referenced by queue.json, uploaded to BrandFlow, approved, or published.

Both generated native PNGs measured **1122x1402**, not 1080x1350, using funzug_pipeline.image_size. Their composition and text were inspected. The headline, readable AI-generated illustration label, and Funzug wordmark are present. The old misleading documentary subheading is absent. Exact native dimensions remain a failed requirement, so both candidates are held outside the queue.

- `assets/2026-10-12-martian-dawn-v2-unvalidated.png`: first generation.
- `assets/2026-10-12-martian-dawn-v3-unvalidated.png`: targeted built-in edit retry.

## Initial prompt

Create exactly ONE original Funzug editorial science image, portrait 4:5, exactly 1080x1350 pixels. Use case scientific-educational. Premium cinematic realistic digital illustration of a dry Martian landscape inspired by wind-carved yardang cliffs near Mount Sharp: distant layered eroded crags under soft early morning light, muted dusty peach sky, cold bluish shadows in the rocky foreground. A cohesive landscape, no rover, no Earth-like clouds, no giant orange sun, no water, no trees, no invented NASA photograph appearance or source logos. Not an exact reconstruction of any observed terrain. Clear visual hierarchy, beautiful restrained contrast and mobile legibility. Include the exact headline 'Mars Wakes In Blue Light' in large elegant readable typography with generous safe margins. Include a clearly readable small label 'AI-generated illustration' underneath the headline so nobody mistakes this for Curiosity's photograph. Include the tasteful small wordmark 'Funzug' near the bottom within safe margins. No other text. Do not include the previous misleading phrase 'Curiosity captured a rare dawn'. Generate one individual final image, never a collage.

## Targeted retry prompt

Edit target: supplied Funzug Mars illustration. Required final raster canvas EXACTLY 1080 pixels wide by 1350 pixels tall, portrait 4:5. The previous raster was 1122x1402, which is invalid. Return native final output at precisely 1080x1350, not an approximate ratio. Preserve the landscape composition, cold bluish foreground shadows, distant warm dusty eroded Martian crags, muted sky, and exact existing text 'Mars Wakes In Blue Light', 'AI-generated illustration', and 'Funzug'. Keep all text within safe margins. Change only the canvas dimensions/framing as necessary. Do not add rover, sun disk, clouds, water, extra words, logos, collage, or documentary-photo claim. One image only.

Source reviewed: https://www.jpl.nasa.gov/news/nasas-curiosity-rover-catches-stunning-martian-dawn/ on 12 October 2026. Its description supports blue foreground hues, distant wind-carved yardangs, and morning lighting. Generated terrain remains conceptual, not a copy or scientific reconstruction of the rover panorama.
