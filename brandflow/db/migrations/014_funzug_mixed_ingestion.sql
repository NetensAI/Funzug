-- No existing image row or approval is rewritten.
ALTER TABLE social_post_drafts ALTER COLUMN image_mime_type DROP NOT NULL;
ALTER TABLE social_post_drafts ALTER COLUMN image_width DROP NOT NULL;
ALTER TABLE social_post_drafts ALTER COLUMN image_height DROP NOT NULL;
ALTER TABLE social_post_drafts DROP CONSTRAINT IF EXISTS funzug_format_image_presence;
ALTER TABLE social_post_drafts ADD CONSTRAINT funzug_format_image_presence CHECK (
 (media_format='image' AND image_mime_type IS NOT NULL AND image_width IS NOT NULL AND image_height IS NOT NULL)
 OR (media_format IN ('carousel','reel') AND image_mime_type IS NULL AND image_width IS NULL AND image_height IS NULL AND image_bytes IS NULL AND image_url IS NULL)
);
