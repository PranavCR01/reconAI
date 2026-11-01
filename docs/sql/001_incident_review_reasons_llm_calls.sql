-- Issue #8: persist why an incident needs review, and every LLM call made for it.
-- Apply in the Supabase SQL editor BEFORE deploying the code that writes these columns.
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS review_reasons jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE rca_incidents ADD COLUMN IF NOT EXISTS llm_calls      jsonb NOT NULL DEFAULT '[]'::jsonb;
