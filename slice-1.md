# Slice 1 — Foundation

## Goal
Establish the project skeleton, data models, Supabase schema, storage adapter, and a working FastAPI health endpoint. No agents, no LangGraph, no LLM calls.

## Demo-able When Complete
Upload a CSV row → it gets parsed, validated against Pydantic schema, and stored in Supabase. `/api/v1/health` returns stack info.

---

## Files to Create

### `backend/models/entities.py`
Pydantic v2 models for all six logical entities:
- `ReconRun` — run_date, sf_org_id, db2_environment (PROD/UAT), status, total_discrepancies
- `ReconRow` — sf_object, sf_field, sf_record_id, sf_value, sf_last_modified, db2_table, db2_column, db2_value, db2_last_updated, last_deployed_at, integration_name, discrepancy_type (Optional), severity (Optional)
- `RCAIncident` — recon_row_id, hypotheses_tested, hypotheses_ruled_out, final_hypothesis, confidence, root_cause_summary, suggested_fix, requires_human_review, status, llm_model, total_tokens_used, latency_ms
- `Evidence` — incident_id, source_type (enum), source_reference, content, relevance_explanation
- `Resolution` — incident_id, confirmed_root_cause, fix_applied, fix_type (enum), fix_verified, ai_was_correct, correction_notes
- `ReconArtifact` — artifact_type, sf_object, sf_field, discrepancy_type, root_cause_category, resolution_confirmed, confidence_score, content, source

Enums needed:
- `DiscrepancyType`: NULL_DOWNSTREAM, MISSING_RECORD, VALUE_MISMATCH, DUPLICATE_DOWNSTREAM, STALE_VALUE
- `Severity`: P1, P2, P3
- `EvidenceSourceType`: splunk_log, sf_field_history, sf_field_permissions, apex_job_log, platform_event_usage, middleware_log, code_chunk, past_incident
- `FixType`: apex_code_change, dataweave_mapping_fix, fls_permission_grant, cdc_channel_config, replay_manual_trigger, middleware_restart, data_backfill, other
- `IncidentStatus`: running, complete, needs_review, escalated

### `backend/models/state.py`
LangGraph state (TypedDict, not Pydantic — LangGraph requirement):
```python
class ReconState(TypedDict):
    recon_row: dict
    current_hypothesis: str
    hypotheses_tested: list[str]
    hypotheses_ruled_out: list[str]
    evidence_collected: list[dict]
    rag_candidates: list[dict]
    reranked_candidates: list[dict]
    root_cause: str | None
    confidence: float | None
    rca_output: dict | None
    iterations: int
    requires_human_review: bool
    llm_calls: list[dict]
    tool_calls: list[dict]
    total_latency_ms: int
```

### `backend/models/outputs.py`
Pydantic models for agent outputs:
- `ClassifiedReconRow` — all ReconRow fields + discrepancy_type + severity (both required)
- `HypothesisDecision` — next_hypothesis (str), tools_to_call (list[str]), reasoning (str), terminate (bool), root_cause (str | None), confidence (float | None)
- `EvidenceResult` — hypothesis_tested, source_type, source_reference, content, relevance_explanation, rules_out (list[str]), confirms (str | None)
- `RCAOutput` — root_cause, confidence, evidence_ids (list[UUID]), similar_past_incidents (list[UUID]), suggested_fix, postmortem_draft, jira_summary, requires_human_review

### `backend/storage/adapter.py`
Abstract base:
```python
class StorageAdapter(ABC):
    async def save_recon_run(self, run: ReconRun) -> str: ...
    async def get_recon_run(self, run_id: str) -> ReconRun: ...
    async def save_recon_row(self, row: ReconRow) -> str: ...
    async def save_rca_incident(self, incident: RCAIncident) -> str: ...
    async def save_evidence(self, evidence: Evidence) -> str: ...
    async def save_resolution(self, resolution: Resolution) -> str: ...
    async def get_incidents_for_run(self, run_id: str) -> list[RCAIncident]: ...
```

### `backend/storage/supabase_adapter.py`
Concrete Supabase implementation using `supabase-py`. All methods async. Use `recon_` prefixed table names.

### `backend/config.py`
```python
class AgentConfig(BaseModel):
    ingestion_llm: str = "claude-haiku-4-5"
    hypothesis_llm: str = "claude-sonnet-4-6"
    evidence_llm: str = "claude-sonnet-4-6"
    reranker_llm: str = "claude-haiku-4-5"
    synthesis_llm: str = "claude-sonnet-4-6"

CONFIGS = {
    "claude": AgentConfig(),
    "groq": AgentConfig(
        ingestion_llm="llama-3.3-70b-versatile",
        hypothesis_llm="llama-3.3-70b-versatile",
        evidence_llm="llama-3.3-70b-versatile",
        reranker_llm="llama-3.3-70b-versatile",
        synthesis_llm="llama-3.3-70b-versatile",
    ),
    "hybrid": AgentConfig(
        ingestion_llm="llama-3.3-70b-versatile",
        reranker_llm="llama-3.3-70b-versatile",
        synthesis_llm="claude-sonnet-4-6",
    ),
}
```

### `backend/main.py`
FastAPI app with only these endpoints for now:
- `GET /api/v1/health` → `{ status, llm_model, vector_store, db, version }`
- `POST /api/v1/recon/runs` → parse body, validate, save ReconRun, return run_id (stub — no analysis yet)

CORS configured for localhost:5173 (Vite dev server).

### `data/sample_fsc_recon.csv`
10 rows covering all 5 discrepancy types. Use realistic FSC objects:
- Contact (MailingCity, Phone, TaxId__c)
- FinancialAccount__c (AnnualIncome__c, AccountStatus__c)
- KYC_Record__c (VerificationStatus__c)
- Address__c (PostalCode, StateCode)

Mix of PROD and UAT environments. Two P1s, four P2s, four P3s. Include a `last_deployed_at` value near the discrepancy timestamp for at least two rows (deployment correlation signal).

---

## Supabase Schema SQL
Run this in Supabase SQL editor before starting:

```sql
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- ReconRun
CREATE TABLE recon_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_date DATE NOT NULL,
    triggered_by TEXT DEFAULT 'manual',
    sf_org_id TEXT NOT NULL,
    db2_environment TEXT NOT NULL CHECK (db2_environment IN ('PROD', 'UAT')),
    total_rows_checked INTEGER DEFAULT 0,
    total_discrepancies INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- ReconRow
CREATE TABLE recon_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES recon_runs(id),
    sf_object TEXT NOT NULL,
    sf_field TEXT NOT NULL,
    sf_record_id TEXT NOT NULL,
    sf_value TEXT,
    sf_last_modified TIMESTAMPTZ,
    sf_modified_by TEXT,
    db2_table TEXT NOT NULL,
    db2_column TEXT NOT NULL,
    db2_value TEXT,
    db2_last_updated TIMESTAMPTZ,
    last_deployed_at TIMESTAMPTZ,
    integration_name TEXT,
    discrepancy_type TEXT,
    severity TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RCAIncident
CREATE TABLE rca_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recon_row_id UUID REFERENCES recon_rows(id),
    hypotheses_tested TEXT[] DEFAULT '{}',
    hypotheses_ruled_out TEXT[] DEFAULT '{}',
    final_hypothesis TEXT,
    confidence FLOAT,
    similar_incidents UUID[] DEFAULT '{}',
    similarity_scores FLOAT[] DEFAULT '{}',
    root_cause_summary TEXT,
    suggested_fix TEXT,
    postmortem_draft TEXT,
    jira_summary TEXT,
    requires_human_review BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'running',
    llm_model TEXT,
    total_tool_calls INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Evidence
CREATE TABLE rca_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES rca_incidents(id),
    source_type TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    content TEXT NOT NULL,
    relevance_explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Resolution
CREATE TABLE resolutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES rca_incidents(id),
    confirmed_root_cause TEXT NOT NULL,
    fix_applied TEXT NOT NULL,
    fix_type TEXT NOT NULL,
    fix_verified BOOLEAN DEFAULT FALSE,
    verification_recon_run_id UUID,
    ai_was_correct BOOLEAN,
    correction_notes TEXT,
    resolved_by TEXT NOT NULL,
    resolved_at TIMESTAMPTZ DEFAULT NOW()
);

-- ArtifactStore (RAG)
CREATE TABLE recon_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    artifact_type TEXT NOT NULL,
    sf_object TEXT,
    sf_field TEXT,
    discrepancy_type TEXT,
    root_cause_category TEXT,
    integration_name TEXT,
    resolution_confirmed BOOLEAN DEFAULT FALSE,
    confidence_score FLOAT,
    content TEXT NOT NULL,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    embedding vector(1536)
);
CREATE INDEX ON recon_artifacts USING hnsw (embedding vector_cosine_ops);

-- RCA Cache
CREATE TABLE rca_cache (
    cache_key TEXT PRIMARY KEY,
    rca_output JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);
```

---

## Environment Variables Needed
```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=          # for embeddings only
GROQ_API_KEY=
LLM_CONFIG=claude        # claude | groq | hybrid
```

---

## Python Dependencies
```
fastapi
uvicorn[standard]
supabase
pydantic>=2.0
python-dotenv
langgraph
langchain-anthropic
langchain-groq
openai                   # for embeddings
python-multipart         # for CSV upload
```

---

## Acceptance Criteria
- [ ] `GET /api/v1/health` returns 200 with stack info
- [ ] `POST /api/v1/recon/runs` accepts the sample CSV, stores a ReconRun in Supabase, returns run_id
- [ ] All Pydantic models import without errors
- [ ] Supabase schema created with all 7 tables
- [ ] `StorageAdapter` ABC and `SupabaseAdapter` implemented
- [ ] `sample_fsc_recon.csv` has 10 realistic FSC rows covering all 5 discrepancy types

## Risk Flag
Supabase pgvector extension must be enabled before schema creation — verify this first. If the free-tier Supabase project doesn't have pgvector enabled, the `recon_artifacts` table creation will fail silently.
