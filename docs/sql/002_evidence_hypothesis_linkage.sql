-- Issue #9: link each evidence row to the hypothesis it was collected for and record
-- what it showed. Apply in the Supabase SQL editor BEFORE deploying the code that uses it.
ALTER TABLE rca_evidence ADD COLUMN IF NOT EXISTS hypothesis_key text;
ALTER TABLE rca_evidence ADD COLUMN IF NOT EXISTS tool           text;
ALTER TABLE rca_evidence ADD COLUMN IF NOT EXISTS tool_args      jsonb;
ALTER TABLE rca_evidence ADD COLUMN IF NOT EXISTS outcome        text;
ALTER TABLE rca_evidence ADD COLUMN IF NOT EXISTS raw_result     jsonb;
