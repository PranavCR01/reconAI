import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { TopBar, Breadcrumbs } from '@/components/layout/TopBar'
import { StatusPill } from '@/components/ui/StatusPill'
import { SeverityBadge } from '@/components/ui/Badge'
import { Panel } from '@/components/ui/Panel'
import { getRun, getRecallMetrics } from '@/lib/api'
import { fmtDate, fmtLatency, fmtConfidence, fmtTokens } from '@/lib/format'
import type { RunDetailResponse, RCAIncident, Severity, BenchmarkResponse, RecallMetrics, LlmConfig } from '@/types'

function StatCell({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 3 }}>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--fg-3)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 22, fontWeight: 700, color: color ?? 'var(--fg)' }}>{value}</span>
    </div>
  )
}

function runStatusVariant(status: string): 'ok' | 'review' | 'analyzing' | 'queued' | 'fail' | 'default' {
  if (status === 'complete') return 'ok'
  if (status === 'running') return 'analyzing'
  if (status === 'error') return 'fail'
  return 'default'
}

interface HypFreq { name: string; count: number }

function buildHypFreq(incidents: RCAIncident[]): HypFreq[] {
  const freq: Record<string, number> = {}
  for (const inc of incidents) {
    for (const h of inc.hypotheses_tested) {
      freq[h] = (freq[h] ?? 0) + 1
    }
  }
  return Object.entries(freq)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
}

interface ObjRow {
  sfObject: string
  count: number
  p1: number
  p2: number
  p3: number
  resolved: number
  avgConf: number
}

function buildByObject(incidents: RCAIncident[]): ObjRow[] {
  const map: Record<string, { count: number; p1: number; p2: number; p3: number; resolved: number; confSum: number; confN: number }> = {}
  for (const inc of incidents) {
    const obj = 'Account' // fallback since sf_object is on ReconRow, not on incident directly
    if (!map[obj]) map[obj] = { count: 0, p1: 0, p2: 0, p3: 0, resolved: 0, confSum: 0, confN: 0 }
    const row = map[obj]
    row.count++
    if (inc.severity === 'P1') row.p1++
    if (inc.severity === 'P2') row.p2++
    if (inc.severity === 'P3') row.p3++
    if (inc.status === 'complete') row.resolved++
    if (inc.confidence != null) { row.confSum += inc.confidence; row.confN++ }
  }
  return Object.entries(map).map(([sfObject, r]) => ({
    sfObject,
    count: r.count,
    p1: r.p1,
    p2: r.p2,
    p3: r.p3,
    resolved: r.resolved,
    avgConf: r.confN > 0 ? r.confSum / r.confN : 0,
  }))
}

const CONFIG_DISPLAY: Record<LlmConfig, string> = {
  claude: 'Claude Haiku / Sonnet',
  groq: 'Groq Llama 3.3 70B',
  hybrid: 'Hybrid (Haiku + Groq)',
}

export default function RunSummary() {
  const { runId } = useParams<{ runId: string }>()
  const [data, setData] = useState<RunDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [recall, setRecall] = useState<RecallMetrics | null>(null)
  const [benchmark] = useState<BenchmarkResponse | null>(null)
  const [jiraModalOpen, setJiraModalOpen] = useState(false)

  function fetchWithRetry<T>(fn: () => Promise<T>, retries = 2, delay = 3000): Promise<T> {
    return fn().catch((e) =>
      retries > 0
        ? new Promise(r => setTimeout(r, delay)).then(() => fetchWithRetry(fn, retries - 1, delay))
        : Promise.reject(e)
    )
  }

  useEffect(() => {
    if (!runId) return
    setLoading(true)
    fetchWithRetry(() => getRun(runId))
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
    getRecallMetrics()
      .then(setRecall)
      .catch(() => { /* non-fatal */ })
  }, [runId])

  function handleDownloadJson() {
    if (!data) return
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `reconai-run-${data.run.id ?? runId}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
        <TopBar center={<Breadcrumbs crumbs={[{ label: 'Runs' }, { label: '…' }]} />} />
        <div style={{ maxWidth: 1320, margin: '0 auto', padding: '18px 24px' }}>
          {[200, 100, 300].map((h, i) => (
            <div key={i} style={{ height: h, borderRadius: 8, background: 'linear-gradient(90deg, var(--bg-2) 0%, var(--bg-3) 50%, var(--bg-2) 100%)', backgroundSize: '200% 100%', animation: 'shimmer 1.4s infinite', marginBottom: 16 }} />
          ))}
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
        <TopBar center={<Breadcrumbs crumbs={[{ label: 'Runs' }, { label: 'Error' }]} />} />
        <div style={{ maxWidth: 1320, margin: '0 auto', padding: '40px 24px', textAlign: 'center', fontFamily: 'var(--mono)', color: 'var(--p1)' }}>
          <div>
            <div style={{ marginBottom: 12 }}>Unable to load run data. The server may be warming up.</div>
            <button
              onClick={() => { setError(null); setLoading(true); fetchWithRetry(() => getRun(runId!)).then(d => { setData(d); setLoading(false) }).catch(e => { setError(String(e)); setLoading(false) }) }}
              style={{ fontFamily: 'var(--mono)', fontSize: 12, background: 'var(--bg-2)', border: '1px solid var(--line)', color: 'var(--fg-1)', padding: '6px 14px', borderRadius: 6, cursor: 'pointer' }}
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    )
  }

  const { run, incidents } = data
  const total = data.total_incidents
  const needsReview = data.needs_review
  const resolvedCount = incidents.filter(i => i.status === 'complete').length
  const p1Count = incidents.filter(i => i.severity === 'P1').length
  const avgConf = incidents.length > 0
    ? incidents.reduce((s, i) => s + (i.confidence ?? 0), 0) / incidents.length
    : 0
  const avgLatency = incidents.length > 0
    ? incidents.reduce((s, i) => s + i.latency_ms, 0) / incidents.length
    : 0

  const hypFreq = buildHypFreq(incidents)
  const maxHypCount = hypFreq.length > 0 ? hypFreq[0].count : 1
  const byObj = buildByObject(incidents)

  const startedStr = fmtDate(run.created_at)
  const finishedStr = fmtDate(run.completed_at)
  const durationMs = run.completed_at && run.created_at
    ? new Date(run.completed_at).getTime() - new Date(run.created_at).getTime()
    : 0

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <TopBar
        center={
          <Breadcrumbs crumbs={[
            { label: 'Runs', to: '/upload' },
            { label: run.id?.slice(0, 8) ?? runId ?? '…' },
            { label: 'Summary' },
          ]} />
        }
      />

      <div style={{ maxWidth: 1320, margin: '0 auto', padding: '18px 24px 80px' }}>
        {/* Run header */}
        <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 8, padding: '16px 20px', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 700, color: 'var(--fg)' }}>
              {run.id?.slice(0, 20) ?? runId}
            </span>
            <span style={{ fontFamily: 'var(--mono)', fontSize: 11, padding: '2px 8px', borderRadius: 4, background: 'var(--bg-3)', border: '1px solid var(--line)', color: 'var(--fg-2)' }}>
              {run.db2_environment}
            </span>
            <StatusPill variant={runStatusVariant(run.status)} />
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
              <button onClick={handleDownloadJson} style={{ padding: '5px 14px', borderRadius: 5, border: '1px solid var(--line)', background: 'var(--bg-2)', color: 'var(--fg-1)', fontFamily: 'var(--mono)', fontSize: 11, cursor: 'pointer' }}>
                Download JSON
              </button>
              <button onClick={() => setJiraModalOpen(true)} style={{ padding: '5px 14px', borderRadius: 5, border: '1px solid var(--info)', background: 'var(--info-bg)', color: 'var(--info)', fontFamily: 'var(--mono)', fontSize: 11, cursor: 'pointer' }}>
                Export to Jira
              </button>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 20, fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--fg-3)', flexWrap: 'wrap' }}>
            <span>Started: <span style={{ color: 'var(--fg-2)' }}>{startedStr}</span></span>
            <span>Finished: <span style={{ color: 'var(--fg-2)' }}>{finishedStr}</span></span>
            {durationMs > 0 && <span>Duration: <span style={{ color: 'var(--fg-2)' }}>{fmtLatency(durationMs)}</span></span>}
            <span>Triggered by: <span style={{ color: 'var(--fg-2)' }}>{run.triggered_by}</span></span>
            <span>SF Org: <span style={{ color: 'var(--fg-2)' }}>{run.sf_org_id}</span></span>
          </div>
        </div>

        {/* Stats row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', borderRadius: 8, border: '1px solid var(--line)', overflow: 'hidden', background: 'var(--bg-1)', marginBottom: 20 }}>
          <StatCell label="Rows Scanned" value={data.rows_scanned ?? run.total_rows_checked ?? 0} />
          <StatCell label="Resolved" value={resolvedCount} color="var(--ok)" />
          <StatCell label="Needs Review" value={needsReview} color="var(--warn)" />
          <StatCell label="P1 Critical" value={p1Count} color="var(--p1)" />
          <StatCell label="Avg Confidence" value={fmtConfidence(avgConf)} />
          <StatCell label="Avg Latency" value={avgLatency > 0 ? fmtLatency(avgLatency) : '—'} />
        </div>

        {/* 2-col grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
          {/* Root Cause Distribution */}
          <Panel title="Root Cause Distribution" meta={`${hypFreq.length} hypotheses`}>
            {hypFreq.length === 0 ? (
              <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-3)', textAlign: 'center', padding: '20px 0' }}>No data</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {hypFreq.map(hf => (
                  <div key={hf.name} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)', width: 160, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{hf.name}</span>
                    <div style={{ flex: 1, height: 16, background: 'var(--bg-2)', borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${Math.round((hf.count / maxHypCount) * 100)}%`, background: 'linear-gradient(90deg, var(--info) 0%, var(--violet) 100%)', borderRadius: 3, transition: 'width 0.4s' }} />
                    </div>
                    <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)', width: 24, textAlign: 'right', flexShrink: 0 }}>{hf.count}</span>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          {/* By Object */}
          <Panel title="By Object">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--mono)', fontSize: 11.5 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    {['SF Object', 'Count', 'Severities', 'Resolved', 'Avg Conf'].map(h => (
                      <th key={h} style={{ padding: '4px 8px', textAlign: 'left', color: 'var(--fg-3)', fontWeight: 500, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {byObj.map(row => (
                    <tr key={row.sfObject} style={{ borderBottom: '1px solid var(--line-soft)' }}>
                      <td style={{ padding: '6px 8px', color: 'var(--fg-1)', fontWeight: 500 }}>{row.sfObject}</td>
                      <td style={{ padding: '6px 8px', color: 'var(--fg-2)' }}>{row.count}</td>
                      <td style={{ padding: '6px 8px' }}>
                        <div style={{ display: 'flex', gap: 4 }}>
                          {row.p1 > 0 && <SeverityBadge severity={'P1' as Severity} size="sm" />}
                          {row.p2 > 0 && <SeverityBadge severity={'P2' as Severity} size="sm" />}
                          {row.p3 > 0 && <SeverityBadge severity={'P3' as Severity} size="sm" />}
                        </div>
                      </td>
                      <td style={{ padding: '6px 8px', color: 'var(--ok)' }}>{row.resolved}/{row.count}</td>
                      <td style={{ padding: '6px 8px', color: 'var(--fg-2)' }}>{fmtConfidence(row.avgConf)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>

        {/* Recall@k */}
        <Panel title="RAG Recall@k" meta="vector retrieval quality · same discrepancy_type = relevant" style={{ marginBottom: 20 }}>
          {recall == null ? (
            <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-3)', padding: '12px 0' }}>
              Computing…
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, padding: '8px 0' }}>
              {([1, 2, 3, 5] as const).map(k => {
                const key = `recall@${k}` as keyof RecallMetrics
                const pct = Math.round((recall[key] ?? 0) * 100)
                return (
                  <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>recall@{k}</span>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 700, color: 'var(--ok)' }}>{pct}%</span>
                    </div>
                    <div style={{ height: 6, background: 'var(--bg-3)', borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${pct}%`, background: 'linear-gradient(90deg, var(--ok), oklch(0.80 0.14 155))', borderRadius: 3 }} />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Panel>

        {/* LLM Comparison */}
        <Panel title="LLM Comparison">
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--mono)', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--line)' }}>
                  {['Model', 'Config', 'Avg Confidence', 'Avg Latency', 'Avg Tokens'].map(h => (
                    <th key={h} style={{ padding: '6px 10px', textAlign: 'left', color: 'var(--fg-3)', fontWeight: 500, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {benchmark ? (
                  benchmark.results.map(row => (
                    <tr key={row.config} style={{ borderBottom: '1px solid var(--line-soft)' }}>
                      <td style={{ padding: '8px 10px', color: 'var(--fg-1)', fontWeight: 500 }}>{CONFIG_DISPLAY[row.config as LlmConfig] ?? row.model}</td>
                      <td style={{ padding: '8px 10px' }}>
                        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, padding: '2px 7px', borderRadius: 4, background: 'var(--bg-3)', border: '1px solid var(--line)', color: 'var(--fg-2)' }}>
                          {row.config}
                        </span>
                      </td>
                      <td style={{ padding: '8px 10px', color: 'var(--ok)', fontWeight: 600 }}>{fmtConfidence(row.avg_confidence)}</td>
                      <td style={{ padding: '8px 10px', color: 'var(--fg-2)' }}>{fmtLatency(row.avg_latency_ms)}</td>
                      <td style={{ padding: '8px 10px', color: 'var(--fg-2)' }}>{fmtTokens(row.avg_tokens)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} style={{ padding: '20px 10px', textAlign: 'center', color: 'var(--fg-3)', fontSize: 11 }}>
                      No benchmark data available
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>

        {/* Jira modal */}
        {jiraModalOpen && (
          <div
            onClick={() => setJiraModalOpen(false)}
            style={{ position: 'fixed', inset: 0, background: 'oklch(0 0 0 / 0.6)', zIndex: 50, display: 'grid', placeItems: 'center' }}
          >
            <div
              onClick={e => e.stopPropagation()}
              style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 12, padding: '28px 32px', maxWidth: 440, width: '90%', display: 'flex', flexDirection: 'column', gap: 16 }}
            >
              <div style={{ fontFamily: 'var(--mono)', fontSize: 13, fontWeight: 700, color: 'var(--fg)' }}>Jira Integration — Coming Soon</div>
              <div style={{ fontFamily: 'var(--sans)', fontSize: 13.5, color: 'var(--fg-2)', lineHeight: 1.6 }}>
                Direct Jira export will be available in a future release. Copy Jira summaries from individual incident detail pages.
              </div>
              <button
                onClick={() => setJiraModalOpen(false)}
                style={{ alignSelf: 'flex-end', padding: '6px 18px', borderRadius: 6, border: '1px solid var(--line)', background: 'var(--bg-2)', color: 'var(--fg-1)', fontFamily: 'var(--mono)', fontSize: 12, cursor: 'pointer' }}
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
