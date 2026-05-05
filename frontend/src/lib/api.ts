import type {
  BenchmarkResponse,
  CreateRunResponse,
  LlmConfig,
  RecallMetrics,
  RunDetailResponse,
  RunIncidentsResponse,
  RCAIncident,
  Evidence,
  ResolveRequest,
  ResolveResponse,
  Environment,
} from '@/types'

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1'

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`API ${res.status}: ${body || res.statusText}`)
  }
  return res.json() as Promise<T>
}

export async function createRun(
  file: File,
  opts: { sfOrgId?: string; environment: Environment }
): Promise<CreateRunResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('sf_org_id', opts.sfOrgId ?? 'sf-demo-org')
  form.append('db2_environment', opts.environment)
  return apiFetch<CreateRunResponse>('/recon/runs', { method: 'POST', body: form })
}

export function getStreamUrl(runId: string, llmConfig?: LlmConfig): string {
  const base = `${API_URL}/recon/runs/${runId}/stream`
  return llmConfig ? `${base}?llm_config=${llmConfig}` : base
}

export async function getRun(runId: string): Promise<RunDetailResponse> {
  return apiFetch<RunDetailResponse>(`/recon/runs/${runId}`)
}

export async function getRunIncidents(runId: string): Promise<RunIncidentsResponse> {
  return apiFetch<RunIncidentsResponse>(`/recon/runs/${runId}/incidents`)
}

export async function getIncident(
  incidentId: string
): Promise<RCAIncident & { evidence: Evidence[] }> {
  return apiFetch<RCAIncident & { evidence: Evidence[] }>(`/incidents/${incidentId}`)
}

export async function resolveIncident(
  incidentId: string,
  body: ResolveRequest
): Promise<ResolveResponse> {
  return apiFetch<ResolveResponse>(`/incidents/${incidentId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function getRecallMetrics(): Promise<RecallMetrics> {
  return apiFetch<RecallMetrics>('/recall')
}

export async function runBenchmark(runId: string, nRows = 2): Promise<BenchmarkResponse> {
  return apiFetch<BenchmarkResponse>(
    `/recon/runs/${runId}/benchmark?n_rows=${nRows}`,
    { method: 'POST' },
  )
}
