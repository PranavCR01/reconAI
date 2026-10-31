-- Issue #11: persist the proposer/critic/judge outcome on each incident.
-- Apply in the Supabase SQL editor BEFORE deploying the code that writes these columns.
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS claims          jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS judge_decision  text;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS revision_count  integer NOT NULL DEFAULT 0;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS prompt_versions jsonb NOT NULL DEFAULT '{}'::jsonb;
