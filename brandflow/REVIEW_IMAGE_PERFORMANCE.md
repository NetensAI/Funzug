# Review image performance

The review page shows eight posts per page and selects metadata plus a database-computed image checksum instead of transferring original image BLOBs. The checksum produces the identical content fingerprint used by the approval endpoint, which still verifies original bytes when approval is submitted.

Single images and carousel slides use private WebP display previews up to 560 by 700 pixels. The complete composition is preserved. Clicking an image opens its original bytes. Preview generation does not update queue entries, stored originals, publication assets, or approvals. The first image loads eagerly; later images load as the reader scrolls.

`scripts/image_preview.py` uses the Pillow runtime already installed in the dashboard image. At most two previews are generated concurrently. Previews are cached by source SHA-256 and renderer version in `/tmp/brandflow-image-previews`, with a maximum of 512 files. A restart clears this disposable cache. Requests check the current active session before accessing cached media or responding with HTTP 304. Browser caching is private and requires revalidation.

No database migration or new credentials are required. Map `social-drafts-page.tsx` to the deployed `app/social-drafts/page.tsx`; deploy the component, image and ordered-media routes, checksum declarations/helper, preview helper/declarations, Python script, and Dockerfile together.

On 19 October 2026, the isolated production smoke instance returned eight cards on page one and six on page two. Its first original was 2,350,994 bytes; the corresponding preview was 77,134 bytes, a 96.7 percent reduction. All eight first-page previews totaled 706,090 bytes. The first cold preview took 411 ms and a cached preview took 17 ms on the Mini PC. Initial server-rendered page time fell from 493 ms to 280 ms. These measurements exclude the user's network and Cloudflare transit.

The production build and TypeScript checks passed. Thirty-seven focused authentication, approval binding, media, and real Pillow compression checks passed. Smoke checks verified original-byte SHA-256 equality, private conditional 304 responses, signed-out access denial, and pagination without modifying any posts.

The old deployed image is retained as `brandflow-dashboard-before-review-speed:20261019`. Original source files are archived at `/home/vatsal/apps/brandflow/.backups/review-speed.HtWame/source.tar`. Only the dashboard service is replaced by this release.
