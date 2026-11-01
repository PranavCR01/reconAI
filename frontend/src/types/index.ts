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

export type EvidenceOutcome = 'supports' | 'refutes' | 'neutral' | 'error' | 'skipped'

export interface Evidence {
  id: string | null
  incident_id: string | null
  source_type: EvidenceSourceType
  source_reference: string
  content: string
  relevance_explanation: string
  created_at: string | null
  hypothesis_key?: string | null
  tool?: string | null
  tool_args?: Record<string, unknown> | null
  outcome?: EvidenceOutcome | null
  raw_result?: Record<string, unknown> | null
}

export type HypothesisVerdict = 'confirmed' | 'refuted' | 'inconclusive'

export interface HypothesisVerdictRecord {
  hypothesis_id: string
  label: string
  kind: string
  category: string
  verdict: HypothesisVerdict
  reason: string
  confidence: number | null
  evidence_ids: string[]
}

export type CriticVerdict = 'supported' | 'unsupported' | 'contradicted'

export interface Claim {
  claim_id: string
  kind: 'root_cause' | 'mechanism' | 'impact' | 'fix' | 'context'
  status: 'established' | 'hypothesis'
  category: string | null
  text: string
  evidence_ids: string[]
  similar_incident_ids: string[]
  hypothesis_ids: string[]
  critic?: { verdict: CriticVerdict; reason: string; stage?: string; evidence_ids?: string[] } | null
}

export interface LLMCallRecord {
  agent: string
  model: string
  attempt?: number
  input_tokens: number
  output_tokens: number
  latency_ms: number
  error?: string
}

export interface TraceStep {
  node: string
  started_at: string
  duration_ms: number
  detail: Record<string, unknown>
  llm_calls: LLMCallRecord[]
}

export interface SimilarIncidentDetail {
  id: string
  similarity: number
  source: string | null
  root_cause_category: string | null
  discrepancy_type: string | null
  summary: string
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
  review_reasons?: string[]
  llm_calls?: LLMCallRecord[]
  hypothesis_verdicts?: HypothesisVerdictRecord[]
  graph_status?: 'confirmed' | 'exhausted' | 'unknown_type' | 'running' | null
  root_cause_category?: string | null
  contributing_factors?: string[]
  graph_version?: string | null
  claims?: Claim[]
  judge_decision?: 'accept' | 'escalate' | null
  revision_count?: number
  prompt_versions?: Record<string, string>
  e2e_latency_ms?: number
  cost_usd?: number | null
  cost_warnings?: string[]
  trace?: TraceStep[]
  recon_row?: ReconRow | null
  evidence_by_hypothesis?: Record<string, Evidence[]>
  similar_incidents_detail?: SimilarIncidentDetail[]
  // Joined fields from ReconRow (populated via SSE or API join)
  severity?: Severity | null
  sf_object?: string | null
  sf_field?: string | null
  // Joined evidence (from GET /incidents/:id)
  evidence?: Evidence[]
  // Existing resolution if already recorded
  resolution?: Resolution | null
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
  rows_scanned: number
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
  status: 'pending' | 'running' | 'complete' | 'error' | 'interrupted'
  integrationName?: string
  p1Count?: number
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

// Analytics — Slice 8
export interface AnalyticsSummary {
  runs: { count: number; delta_pct: number }
  incidents_triaged: { count: number; delta_pct: number }
  avg_resolution_rate: { pct: number; delta_pt: number }
  avg_confidence: { pct: number; delta_pt: number }
  top_root_cause: { name: string; pct: number; count: number }
  deploy_correlations: { count: number; total_deploys: number }
}

export interface IncidentsOverTimeResponse {
  dates: string[]
  series: Record<string, number[]>
  deployments: { date: string; name: string }[]
}

export interface ByObjectRow {
  object: string
  p1: number
  p2: number
  p3: number
  total: number
}

export interface RootCauseRow {
  root_cause: string
  count: number
  pct: number
}

export interface AIAccuracyResponse {
  weeks: string[]
  recall_at_1: number[]
  recall_at_3: number[]
  ai_was_correct: number[]
  summary: {
    recall_at_1: number
    recall_at_3: number
    resolutions: number
    overrides: number
  }
}

export interface DeploymentCorrelation {
  deploy_name: string
  description: string | null
  deployed_at: string
  deploy_type: string
  incidents_24h: number
  sigma: number
  most_affected_object: string | null
  suspected_root_cause: string | null
  status: 'investigating' | 'resolved' | 'normal'
}
