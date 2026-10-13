-- Additive storage only. Existing image bytes and approval records are untouched.
ALTER TABLE social_post_drafts ADD COLUMN IF NOT EXISTS media_format text NOT NULL DEFAULT 'image'
  CHECK (media_format IN ('image','carousel','reel'));

CREATE TABLE IF NOT EXISTS social_post_media_assets (
  draft_id uuid NOT NULL REFERENCES social_post_drafts(id) ON DELETE RESTRICT,
  media_index integer NOT NULL CHECK (media_index BETWEEN 0 AND 9),
  mime_type text NOT NULL CHECK (mime_type IN ('image/png','image/jpeg','video/mp4')),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > width AND abs(width::bigint*5-height::bigint*4) <= 2),
  duration_ms integer,
  media_bytes bytea NOT NULL CHECK (octet_length(media_bytes) BETWEEN 1 AND 104857600),
  sha256 text GENERATED ALWAYS AS (encode(sha256(media_bytes),'hex')) STORED,
  PRIMARY KEY (draft_id,media_index),
  UNIQUE (draft_id,sha256),
  CHECK ((mime_type IN ('image/png','image/jpeg') AND duration_ms IS NULL AND octet_length(media_bytes)<=12582912)
     OR (mime_type='video/mp4' AND duration_ms IS NOT NULL AND duration_ms BETWEEN 1 AND 180000))
);

CREATE OR REPLACE FUNCTION funzug_guard_ordered_media() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_id uuid; draft_status text; draft_format text;
BEGIN
  IF TG_OP='UPDATE' AND NEW.draft_id<>OLD.draft_id THEN
    RAISE EXCEPTION 'Reviewed media cannot move between drafts';
  END IF;
  target_id := CASE WHEN TG_OP='DELETE' THEN OLD.draft_id ELSE NEW.draft_id END;
  SELECT status,media_format INTO draft_status,draft_format FROM social_post_drafts WHERE id=target_id FOR UPDATE;
  IF NOT FOUND OR draft_status<>'pending_review' THEN
    RAISE EXCEPTION 'Reviewed media is immutable';
  END IF;
  IF TG_OP<>'DELETE' THEN
    IF draft_format='image' OR (draft_format='carousel' AND NEW.mime_type NOT IN ('image/png','image/jpeg'))
       OR (draft_format='reel' AND (NEW.media_index<>0 OR NEW.mime_type<>'video/mp4')) THEN
      RAISE EXCEPTION 'Media does not match draft format';
    END IF;
    RETURN NEW;
  END IF;
  RETURN OLD;
END $$;

DROP TRIGGER IF EXISTS funzug_ordered_media_guard ON social_post_media_assets;
CREATE TRIGGER funzug_ordered_media_guard BEFORE INSERT OR UPDATE OR DELETE ON social_post_media_assets
  FOR EACH ROW EXECUTE FUNCTION funzug_guard_ordered_media();

CREATE OR REPLACE FUNCTION funzug_guard_media_approval() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE asset_count integer; first_index integer; last_index integer;
BEGIN
  IF TG_OP='UPDATE' AND NEW.media_format<>OLD.media_format THEN
    IF OLD.status<>'pending_review' THEN
      RAISE EXCEPTION 'Reviewed format is immutable';
    END IF;
    IF EXISTS(SELECT 1 FROM social_post_media_assets WHERE draft_id=NEW.id) THEN
      RAISE EXCEPTION 'Clear pending assets before changing format';
    END IF;
  END IF;
  IF NEW.status='approved' AND NEW.media_format<>'image' THEN
    SELECT count(*),min(media_index),max(media_index) INTO asset_count,first_index,last_index
      FROM social_post_media_assets WHERE draft_id=NEW.id;
    IF first_index<>0 OR last_index<>asset_count-1 OR
       (NEW.media_format='carousel' AND asset_count NOT BETWEEN 2 AND 10) OR
       (NEW.media_format='reel' AND asset_count<>1) THEN
      RAISE EXCEPTION 'Complete ordered media required before approval';
    END IF;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS funzug_media_approval_guard ON social_post_drafts;
CREATE TRIGGER funzug_media_approval_guard BEFORE INSERT OR UPDATE ON social_post_drafts
  FOR EACH ROW EXECUTE FUNCTION funzug_guard_media_approval();
