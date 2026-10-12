BEGIN;
ALTER TABLE social_post_drafts DROP CONSTRAINT IF EXISTS social_post_drafts_image_width_check;
ALTER TABLE social_post_drafts DROP CONSTRAINT IF EXISTS social_post_drafts_image_height_check;
ALTER TABLE social_post_drafts DROP CONSTRAINT IF EXISTS social_post_drafts_native_portrait_ratio;
ALTER TABLE social_post_drafts ADD CONSTRAINT social_post_drafts_native_portrait_ratio
  CHECK (image_width > 0 AND image_height > 0 AND image_width::bigint * 5 = image_height::bigint * 4);
COMMIT;
