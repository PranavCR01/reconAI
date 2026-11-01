-- Issue #10: persist the hypothesis graph's outcome on each incident.
-- Apply in the Supabase SQL editor BEFORE deploying the code that writes these columns.
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS hypothesis_verdicts  jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS graph_status         text;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS root_cause_category  text;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS contributing_factors jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS graph_version        text;
