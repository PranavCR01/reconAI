-- Issue #12: per-incident trace, wall-clock latency and cost.
-- Apply in the Supabase SQL editor BEFORE deploying the code that writes these columns.
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS e2e_latency_ms integer NOT NULL DEFAULT 0;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS cost_usd       numeric(12, 6);
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS cost_warnings  jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS trace          jsonb NOT NULL DEFAULT '[]'::jsonb;
