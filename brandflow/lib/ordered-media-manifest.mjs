import {createHash} from 'node:crypto';
import {reviewedMediaHash} from './funzug-content-hash.mjs';

// Build a review package from private database bytes, never public URLs or
// caller-supplied hashes. Delivery remains disabled until review is integrated.
export function orderedMediaManifest(row, assets) {
  if (!['carousel', 'reel'].includes(row.media_format) || !Array.isArray(assets))
    throw Error('Unsupported ordered media package');
  const media = assets.map((asset, index) => {
    if (asset.draft_id !== row.id || asset.asset_index !== index)
      throw Error('Ordered media parent or index mismatch');
    if (!Buffer.isBuffer(asset.media_bytes)) throw Error('Private media bytes required');
    const hash = createHash('sha256').update(asset.media_bytes).digest('hex');
    if (asset.sha256 !== hash) throw Error('Stored media checksum mismatch');
    return {
      mimeType: asset.mime_type, width: asset.width, height: asset.height,
      data: asset.media_bytes.toString('base64'),
      ...(row.media_format === 'reel' ? {durationMs: asset.duration_ms} : {}),
    };
  });
  const draft = {
    headline: row.headline, caption: row.caption, claims: row.claims,
    sources: row.evidence_sources, platforms: row.platforms,
    format: row.media_format, media,
  };
  return {draft, contentHash: reviewedMediaHash(draft)};
}
