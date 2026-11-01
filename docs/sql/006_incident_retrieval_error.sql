-- Issue #15: record a failed similar-incident retrieval on the incident (distinct from zero results).
-- Apply in the Supabase SQL editor BEFORE deploying the code that writes this column.
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS retrieval_error text;
