// Mirrors backend Pydantic models (backend/models/entities.py, outputs.py)

export type Severity = 'P1' | 'P2' | 'P3'

export type DiscrepancyType =
  | 'NULL_DOWNSTREAM'
  | 'MISSING_RECORD'
  | 'VALUE_MISMATCH'
  | 'DUPLICATE_DOWNSTREAM'
  | 'STALE_VALUE'

export type EvidenceSourceType =
  | 'splunk_log'
  | 'sf_field_history'
  | 'sf_field_permissions'
  | 'apex_job_log'
  | 'platform_event_usage'
  | 'middleware_log'
  | 'code_chunk'
  | 'past_incident'

export type FixType =
  | 'apex_code_change'
  | 'dataweave_mapping_fix'
  | 'fls_permission_grant'
  | 'cdc_channel_config'
  | 'replay_manual_trigger'
  | 'middleware_restart'
  | 'data_backfill'
  | 'other'

export type IncidentStatus = 'running' | 'complete' | 'needs_review' | 'escalated'

export interface ReconRun {
  id: string | null
  run_date: string
  triggered_by: string
  sf_org_id: string
  db2_environment: string
  total_rows_checked: number
  total_discrepancies: number
  status: string
  created_at: string | null
  completed_at: string | null
}

export interface ReconRow {
  id: string | null
  run_id: string | null
  sf_object: string
  sf_field: string
  sf_record_id: string
  sf_value: string | null
  sf_last_modified: string | null
  sf_modified_by: string | null
  db2_table: string
  db2_column: string
  db2_value: string | null
  db2_last_updated: string | null
  last_deployed_at: string | null
  integration_name: string | null
  discrepancy_type: DiscrepancyType | null
  severity: Severity | null
  created_at: string | null
}

export interface Evidence {
  id: string | null
  incident_id: string | null
  source_type: EvidenceSourceType
  source_reference: string
  content: string
  relevance_explanation: string
  created_at: string | null
}

export interface RCAIncident {
  id: string | null
  recon_row_id: string | null
  hypotheses_tested: string[]
  hypotheses_ruled_out: string[]
  final_hypothesis: string | null
  confidence: number | null
  similar_incidents: string[]
  similarity_scores: number[]
  root_cause_summary: string | null
  suggested_fix: string | null
  postmortem_draft: string | null
  jira_summary: string | null
  requires_human_review: boolean
  status: IncidentStatus
  llm_model: string | null
  total_tool_calls: number
  total_tokens_used: number
  latency_ms: number
  created_at: string | null
  // Joined fields from ReconRow (populated via SSE or API join)
  severity?: Severity | null
  sf_object?: string | null
  sf_field?: string | null
  // Joined evidence (from GET /incidents/:id)
  evidence?: Evidence[]
}

export interface Resolution {
  id: string | null
  incident_id: string | null
  confirmed_root_cause: string
  fix_applied: string
  fix_type: FixType
  fix_verified: boolean
  verification_recon_run_id: string | null
  ai_was_correct: boolean | null
  correction_notes: string | null
  resolved_by: string
  resolved_at: string | null
}

// SSE event payloads from GET /recon/runs/:id/stream
export interface SSEIncidentEvent {
  row_index: number
  row_id: string
  incident_id: string | null
  cached: boolean
  severity: Severity | null
  sf_object: string | null
  sf_field: string | null
  root_cause_summary: string | null
  confidence: number | null
  requires_human_review: boolean
  jira_summary: string | null
  llm_model: string | null
}

export interface SSEDoneEvent {
  total_rows: number
}

export interface SSEErrorEvent {
  row_index: number
  row_id: string
  error: string
}

// GET /recon/runs/:id response shape
export interface RunDetailResponse {
  run: ReconRun
  incidents: (RCAIncident & { severity: Severity | null })[]
  total_incidents: number
  needs_review: number
}

// GET /recon/runs/:id/incidents response
export interface RunIncidentsResponse {
  run_id: string
  incidents: (RCAIncident & { severity: Severity | null })[]
}

// POST /recon/runs response
export interface CreateRunResponse {
  run_id: string
  rows_accepted: number
}

// POST /incidents/:id/resolve response
export interface ResolveResponse {
  resolution_id: string
}

// POST /incidents/:id/resolve body
export interface ResolveRequest {
  confirmed_root_cause: string
  fix_applied: string
  fix_type: FixType
  fix_verified?: boolean
  resolved_by: string
  correction_notes?: string
  ai_was_correct?: boolean
}

// LocalStorage run history entry
export interface RunHistoryEntry {
  runId: string
  createdAt: string
  environment: 'PROD' | 'UAT'
  sfOrgId: string
  rowCount: number
  status: 'pending' | 'running' | 'complete' | 'error'
  integrationName?: string
}

// Derived UI types
export type LlmConfig = 'claude' | 'groq' | 'hybrid'
export type Environment = 'PROD' | 'UAT'
export type RunStatus = 'idle' | 'uploading' | 'streaming' | 'complete' | 'error'

// Benchmark types — POST /api/v1/recon/runs/:id/benchmark
export interface BenchmarkConfigRow {
  config: LlmConfig
  model: string
  avg_latency_ms: number
  avg_tokens: number
  avg_confidence: number
}

export interface BenchmarkResponse {
  run_id: string
  rows_sampled: number
  results: BenchmarkConfigRow[]
}

// Recall@k — GET /api/v1/recall
export interface RecallMetrics {
  'recall@1': number
  'recall@2': number
  'recall@3': number
  'recall@5': number
}
