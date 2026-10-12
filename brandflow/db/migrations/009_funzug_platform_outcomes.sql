ALTER TABLE social_post_drafts ADD COLUMN IF NOT EXISTS platform_outcomes jsonb NOT NULL DEFAULT '{}'::jsonb;
