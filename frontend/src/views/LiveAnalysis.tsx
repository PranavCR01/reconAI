import { useCallback, useEffect, useRef, useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { TopBar, Breadcrumbs } from '@/components/layout/TopBar'
import { StatusPill } from '@/components/ui/StatusPill'
import { SeverityBadge } from '@/components/ui/Badge'
import { ConfidenceBar } from '@/components/ui/ConfidenceBar'
import { HypothesisPills } from '@/components/ui/HypothesisPills'
import type { HypothesisItem } from '@/components/ui/HypothesisPills'
import { EvidenceChip } from '@/components/ui/EvidenceChip'
import { Panel } from '@/components/ui/Panel'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import type { SegOption } from '@/components/ui/SegmentedControl'
import { useReconStore, updateRunInHistory } from '@/store/reconStore'
import { connectToRun } from '@/lib/sse'
import { getRunIncidents, getRun } from '@/lib/api'
import { fmtLatency, fmtTokens, fmtCurrency } from '@/lib/format'
import type { RCAIncident, SSEIncidentEvent, Severity } from '@/types'

const SEV_COLOR: Record<string, string> = {
  P1: 'var(--p1)',
  P2: 'var(--p2)',
  P3: 'var(--p3)',
}

function sseToIncident(e: SSEIncidentEvent): RCAIncident {
  const done = !!e.root_cause_summary
  return {
    id: e.incident_id,
    recon_row_id: e.row_id,
    hypotheses_tested: [],
    hypotheses_ruled_out: [],
    final_hypothesis: null,
    confidence: e.confidence,
    similar_incidents: [],
    similarity_scores: [],
    root_cause_summary: e.root_cause_summary,
    suggested_fix: null,
    postmortem_draft: null,
    jira_summary: e.jira_summary,
    requires_human_review: e.requires_human_review,
    status: done ? (e.requires_human_review ? 'needs_review' : 'complete') : 'running',
    llm_model: e.llm_model,
    total_tool_calls: 0,
    total_tokens_used: 0,
    latency_ms: 0,
    created_at: null,
    severity: e.severity,
    sf_object: e.sf_object,
    sf_field: e.sf_field,
    evidence: [],
  }
}

function buildHypItems(tested: string[], ruledOut: string[]): HypothesisItem[] {
  return tested.map(h => ({ name: h, state: (ruledOut.includes(h) ? 'fail' : 'done') as HypothesisItem['state'] }))
}

function statusVariant(inc: RCAIncident): 'ok' | 'review' | 'analyzing' | 'queued' | 'fail' | 'default' {
  if (inc.status === 'complete') return 'ok'
  if (inc.status === 'needs_review') return 'review'
  if (inc.status === 'escalated') return 'fail'
  if (inc.status === 'running') return 'analyzing'
  return 'queued'
}

function StatCell({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ padding: '10px 16px', display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--fg-3)' }}>{label}</span>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 20, fontWeight: 700, color: color ?? 'var(--fg)' }}>{value}</span>
    </div>
  )
}

const AGENT_STEPS = [
  { label: 'Schema diff', desc: 'SF field vs DB2 column type check' },
  { label: 'FLS pull', desc: 'Field-level security permissions' },
  { label: 'DB2 query', desc: 'Downstream value lookup' },
  { label: 'Hypothesis ranking', desc: 'LLM hypothesis scoring' },
  { label: 'Remediation', desc: 'Suggested fix generation' },
  { label: 'Confidence', desc: 'Final confidence scoring' },
]

const SOURCE_CONNECTIONS = [
  { name: 'Salesforce FSC', ok: true },
  { name: 'DB2 Warehouse', ok: true },
  { name: 'Splunk', ok: true },
  { name: 'MuleSoft', ok: false },
  { name: 'GitHub', ok: true },
]

export default function LiveAnalysis() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const store = useReconStore()
  const [tab, setTab] = useState('all')
  const [sevFilter, setSevFilter] = useState<Severity | 'all'>('all')
  const [startTime] = useState(() => Date.now())
  const [elapsed, setElapsed] = useState(0)
  const [isDone, setIsDone] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [sseError, setSseError] = useState(false)
  const [retryKey, setRetryKey] = useState(0)
  const [totalRows, setTotalRows] = useState(0)
  const [cacheHits, setCacheHits] = useState(0)
  const [analyzedCount, setAnalyzedCount] = useState(0)
  const [expectedRows, setExpectedRows] = useState(0)
  const [apiStats, setApiStats] = useState<{ avgTokens: number; totalCalls: number; avgLatencyMs: number; count: number } | null>(null)
  const sseCleanupRef = useRef<(() => void) | null>(null)
  const sseOpenedRef = useRef(false)

  const handleStop = useCallback(() => {
    if (sseCleanupRef.current) {
      sseCleanupRef.current()
      sseCleanupRef.current = null
    }
    store.setSseConnected(false)
    setIsPaused(true)
  }, [store])

  useEffect(() => {
    const id = setInterval(() => setElapsed(Date.now() - startTime), 1000)
    return () => clearInterval(id)
  }, [startTime])

  useEffect(() => {
    if (!runId) return
    getRun(runId).then(data => setExpectedRows(data.rows_scanned)).catch(() => {})
  }, [runId])

  useEffect(() => {
    if (!runId) return
    if (sseOpenedRef.current) return
    sseOpenedRef.current = true
    store.setRunId(runId)
    const cleanup = connectToRun(runId, {
      onIncident: (e) => {
        store.upsertIncident(sseToIncident(e))
        store.setSseConnected(true)
        store.setRunStatus('streaming')
        if (e.cached) setCacheHits(n => n + 1)
        if (e.root_cause_summary) setAnalyzedCount(n => n + 1)
      },
      onDone: async (e) => {
        store.setRunStatus('complete')
        store.setSseConnected(false)
        setIsDone(true)
        setTotalRows(e.total_rows)
        sseCleanupRef.current = null
        if (runId) updateRunInHistory(runId, { status: 'complete' })
        if (runId) {
          try {
            const { incidents: fresh } = await getRunIncidents(runId)
            console.log('[DONE] first incident from API:', JSON.stringify(fresh[0]).slice(0, 300))
            // Enrich store entries with hypothesis data from DB (not in SSE)
            for (const inc of fresh) {
              if (!inc.recon_row_id) continue
              store.upsertIncident({ ...inc, sf_object: inc.sf_object, sf_field: inc.sf_field })
            }
            // Compute run stats directly from API response — do not rely on
            // the Map merge since SSE events carry zero for tokens/latency.
            const n = fresh.length
            if (n > 0) {
              setApiStats({
                avgTokens: Math.round(fresh.reduce((s, i) => s + (i.total_tokens_used ?? 0), 0) / n),
                totalCalls: fresh.reduce((s, i) => s + (i.total_tool_calls ?? 0), 0),
                avgLatencyMs: fresh.reduce((s, i) => s + (i.latency_ms ?? 0), 0) / n,
                count: n,
              })
            }
          } catch {
            // non-fatal; stats stay at 0 rather than crashing
          }
        }
      },
      onError: () => {
        store.setSseConnected(false)
        if (!isDone) setSseError(true)
      },
    }, store.llmConfig)
    sseCleanupRef.current = cleanup
    return () => {
      cleanup()
      sseCleanupRef.current = null
      sseOpenedRef.current = false
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, retryKey])

  const allIncidents = store.getIncidentsSorted()
  const total = allIncidents.length
  const p1Count = allIncidents.filter(i => i.severity === 'P1').length
  const p2Count = allIncidents.filter(i => i.severity === 'P2').length
  const p3Count = allIncidents.filter(i => i.severity === 'P3').length
  // resolvedCount: only 'complete' (not needs_review) — used for Resolved stat cell and tab
  const resolvedCount = allIncidents.filter(i => i.status === 'complete').length
  const needsReviewCount = allIncidents.filter(i => i.requires_human_review === true).length
  const analyzingCount = Math.max(0, (expectedRows || totalRows) - analyzedCount)
  const cacheHitPct = total > 0 ? Math.min(100, Math.round((cacheHits / total) * 100)) : null

  // Stats sourced from API response after done — reliable since SSE carries zero for these
  const displayAvgTokens = apiStats?.avgTokens ?? 0
  const displayTotalCalls = apiStats?.totalCalls ?? 0
  const displayCount = apiStats?.count ?? total
  const displayAvgLatencyMs = apiStats?.avgLatencyMs ?? 0
  const displayAvgCalls = displayCount > 0 ? (displayTotalCalls / displayCount).toFixed(1) : '—'
  const displayApproxSpend = displayAvgTokens > 0 ? displayAvgTokens * displayCount * 0.000003 : 0

  // Progress bar denominator: use SSE done event total when known, else Map size
  const progressTotal = totalRows || total

  const topObjects = useMemo(() => {
    const counts = new Map<string, number>()
    for (const inc of allIncidents) {
      const obj = inc.sf_object ?? 'Unknown'
      counts.set(obj, (counts.get(obj) ?? 0) + 1)
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
  }, [allIncidents])
  const elapsedSec = Math.floor(elapsed / 1000)
  const etaStr = progressTotal > 0 && analyzedCount < progressTotal
    ? `~${Math.max(0, Math.round((progressTotal - analyzedCount) * elapsedSec / Math.max(analyzedCount, 1)))}s`
    : progressTotal > 0 ? 'Done' : '…'

  const tabOptions: SegOption[] = [
    { value: 'all', label: 'All', sub: String(total) },
    { value: 'review', label: 'Needs Review', sub: String(needsReviewCount) },
    { value: 'complete', label: 'Resolved', sub: String(resolvedCount) },
  ]

  const filtered = useMemo(() => {
    let list = allIncidents
    if (tab === 'review') list = list.filter(i => i.status === 'needs_review')
    if (tab === 'complete') list = list.filter(i => i.status === 'complete')
    if (sevFilter !== 'all') list = list.filter(i => i.severity === sevFilter)
    return list
  }, [allIncidents, tab, sevFilter])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <TopBar
        center={
          <Breadcrumbs crumbs={[
            { label: 'Runs', to: '/' },
            { label: runId ?? '…' },
            { label: 'Live Analysis' },
          ]} />
        }
        right={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {store.sseConnected && !isPaused && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ok)' }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--ok)', animation: 'blink-dot 1.2s ease-in-out infinite' }} />
                LIVE
              </span>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 10px', background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 6 }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>
                {analyzedCount}/{progressTotal || '?'} analyzed
              </span>
              <div style={{ width: 80, height: 4, background: 'var(--bg-3)', borderRadius: 2, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: progressTotal > 0 ? `${Math.round((analyzedCount / progressTotal) * 100)}%` : '0%', background: 'var(--ok)', borderRadius: 2, transition: 'width 0.4s' }} />
              </div>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>ETA {etaStr}</span>
            </div>
            {store.sseConnected && !isPaused && (
              <button
                onClick={handleStop}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '4px 10px', borderRadius: 5,
                  border: '1px solid var(--line)',
                  background: 'var(--bg-2)', color: 'var(--warn)',
                  fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: 1, background: 'var(--warn)' }} />
                Stop
              </button>
            )}
          </div>
        }
      />

      {/* SSE error banner */}
      {sseError && !isDone && (
        <div style={{
          background: 'oklch(0.18 0.04 45)',
          borderBottom: '1px solid oklch(0.55 0.16 45)',
          padding: '10px 18px',
          display: 'flex', alignItems: 'center', gap: 10,
          fontFamily: 'var(--mono)', fontSize: 12,
          color: 'oklch(0.80 0.10 45)',
        }}>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ flexShrink: 0 }}>
            <circle cx="8" cy="8" r="6" /><path d="M8 5v3M8 10v.5" />
          </svg>
          Analysis interrupted — the service may be temporarily unavailable. Your partial results are shown above.
          <button
            onClick={() => { setSseError(false); setRetryKey(k => k + 1) }}
            style={{
              marginLeft: 'auto',
              height: 26, padding: '0 12px', borderRadius: 5,
              border: '1px solid oklch(0.55 0.16 45)',
              background: 'oklch(0.22 0.05 45)',
              color: 'oklch(0.80 0.10 45)',
              fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Stats bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', borderBottom: '1px solid var(--line)', background: 'var(--bg-1)' }}>
        <StatCell label="Discrepancies" value={total} />
        <StatCell label="P1 Critical" value={p1Count} color="var(--p1)" />
        <StatCell label="Resolved" value={resolvedCount} color="var(--ok)" />
        <StatCell label="Needs Review" value={needsReviewCount} color="var(--warn)" />
        <StatCell label="Analyzing" value={analyzingCount} />
        <StatCell label="Mean Time / Incident" value={displayAvgLatencyMs > 0 ? fmtLatency(displayAvgLatencyMs) : '—'} />
      </div>

      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 18px', borderBottom: '1px solid var(--line)', background: 'var(--bg-1)', flexWrap: 'wrap' }}>
        <SegmentedControl options={tabOptions} value={tab} onChange={setTab} />
        <div style={{ display: 'flex', gap: 6 }}>
          {(['all', 'P1', 'P2', 'P3'] as const).map(s => (
            <button
              key={s}
              onClick={() => setSevFilter(s as Severity | 'all')}
              style={{
                padding: '3px 10px', borderRadius: 5,
                border: `1px solid ${sevFilter === s ? 'var(--line)' : 'transparent'}`,
                background: sevFilter === s ? 'var(--bg-3)' : 'transparent',
                color: s === 'all' ? 'var(--fg-2)' : SEV_COLOR[s],
                fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 500, cursor: 'pointer',
              }}
            >
              {s === 'all' ? 'All severities' : s}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          {store.sseConnected && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ok)' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--ok)', animation: 'blink-dot 1.2s ease-in-out infinite' }} />
              streaming
            </span>
          )}
        </div>
      </div>

      {/* Main grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', minHeight: 'calc(100vh - 210px)' }}>
        {/* Feed */}
        <div style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 10, borderRight: '1px solid var(--line)' }}>
          <AnimatePresence>
            {isPaused && !isDone && (
              <motion.div
                key="paused-banner"
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 14px',
                  borderRadius: 8,
                  background: 'oklch(0.24 0.05 75 / 0.4)',
                  border: '1px solid oklch(0.50 0.13 75)',
                  flexShrink: 0,
                }}
              >
                <span style={{ color: 'var(--warn)', fontSize: 14, lineHeight: 1 }}>⏸</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--warn)', fontWeight: 600 }}>
                  Analysis paused
                </span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>·</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>
                  {resolvedCount} of {total || '…'} incidents streamed
                </span>
                <button
                  onClick={() => navigate(`/runs/${runId}/summary`)}
                  style={{
                    marginLeft: 'auto',
                    padding: '4px 12px',
                    borderRadius: 5,
                    border: '1px solid oklch(0.50 0.13 75)',
                    background: 'oklch(0.28 0.06 75 / 0.5)',
                    color: 'var(--warn)',
                    fontFamily: 'var(--mono)',
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  View Summary →
                </button>
              </motion.div>
            )}
          </AnimatePresence>
          <AnimatePresence>
            {isDone && (
              <motion.div
                key="done-banner"
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 14px',
                  borderRadius: 8,
                  background: 'oklch(0.24 0.05 155 / 0.5)',
                  border: '1px solid oklch(0.45 0.12 155)',
                  flexShrink: 0,
                }}
              >
                <span style={{ color: 'var(--ok)', fontSize: 14, lineHeight: 1 }}>✓</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--ok)', fontWeight: 600 }}>
                  Analysis complete
                </span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>·</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>
                  {totalRows} rows analyzed
                </span>
                <button
                  onClick={() => navigate(`/runs/${runId}/summary`)}
                  style={{
                    marginLeft: 'auto',
                    padding: '4px 12px',
                    borderRadius: 5,
                    border: '1px solid oklch(0.45 0.12 155)',
                    background: 'oklch(0.30 0.07 155 / 0.6)',
                    color: 'var(--ok)',
                    fontFamily: 'var(--mono)',
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                >
                  View Summary →
                </button>
              </motion.div>
            )}
          </AnimatePresence>
          <AnimatePresence initial={false}>
            {filtered.map(inc => (
              <IncidentCard key={inc.id ?? inc.recon_row_id ?? String(Math.random())} incident={inc} runId={runId ?? ''} />
            ))}
          </AnimatePresence>
          {filtered.length === 0 && (
            <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--fg-3)', fontFamily: 'var(--mono)', fontSize: 13 }}>
              Waiting for incidents…
            </div>
          )}
        </div>

        {/* Right rail */}
        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Panel title="Agent Pipeline">
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {AGENT_STEPS.map((step, i) => (
                <div key={step.label} style={{ display: 'flex', gap: 10, padding: '7px 0', borderBottom: i < AGENT_STEPS.length - 1 ? '1px solid var(--line-soft)' : 'none' }}>
                  <div style={{ width: 20, height: 20, borderRadius: '50%', background: 'var(--ok-bg)', border: '1px solid var(--ok)', display: 'grid', placeItems: 'center', flexShrink: 0 }}>
                    <span style={{ fontSize: 10, color: 'var(--ok)' }}>✓</span>
                  </div>
                  <div>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 11.5, fontWeight: 500, color: 'var(--fg-1)' }}>{step.label}</div>
                    <div style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--fg-3)', marginTop: 1 }}>{step.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Run Stats">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { label: 'Tokens / incident', value: displayAvgTokens > 0 ? fmtTokens(displayAvgTokens) : '—' },
                { label: 'Avg tool calls', value: displayTotalCalls > 0 ? displayAvgCalls : '—' },
                { label: 'Cache hit %', value: cacheHitPct !== null ? `${cacheHitPct}%` : '—' },
                { label: 'Approx. spend', value: displayApproxSpend > 0 ? fmtCurrency(displayApproxSpend) : '—' },
              ].map(row => (
                <div key={row.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>{row.label}</span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 600, color: 'var(--fg-1)' }}>{row.value}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Source Connections">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              {SOURCE_CONNECTIONS.map(src => (
                <div key={src.name} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--fg-1)' }}>{src.name}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontFamily: 'var(--mono)', fontSize: 10.5, color: src.ok ? 'var(--ok)' : 'var(--warn)' }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: src.ok ? 'var(--ok)' : 'var(--warn)' }} />
                    {src.ok ? 'connected' : 'degraded'}
                  </span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Top SF Objects">
            {topObjects.length === 0 ? (
              <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)', textAlign: 'center', padding: '12px 0' }}>
                Waiting for data…
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {topObjects.map(([obj, count]) => (
                  <div key={obj} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-1)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '75%' }}>{obj}</span>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--fg-3)', flexShrink: 0 }}>{count}</span>
                    </div>
                    <div style={{ height: 4, background: 'var(--bg-3)', borderRadius: 2, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${total > 0 ? (count / total) * 100 : 0}%`, background: 'var(--info)', borderRadius: 2, transition: 'width 0.4s' }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}

function IncidentCard({ incident: inc, runId }: { incident: RCAIncident; runId: string }) {
  const navigate = useNavigate()
  const isAnalyzing = inc.status === 'running'
  const borderColor = inc.severity ? SEV_COLOR[inc.severity] : 'var(--line)'
  const hypItems = buildHypItems(inc.hypotheses_tested, inc.hypotheses_ruled_out)

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
      style={{
        background: isAnalyzing
          ? 'linear-gradient(135deg, var(--bg-1) 0%, oklch(0.22 0.05 220 / 0.4) 100%)'
          : 'var(--bg-1)',
        border: '1px solid var(--line)',
        borderLeft: `3px solid ${borderColor}`,
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderBottom: '1px solid var(--line-soft)' }}>
        <SeverityBadge severity={inc.severity} />
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--info)' }}>SF → DB2</span>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>{inc.recon_row_id ?? '—'}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {inc.requires_human_review && (
            <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--warn)', background: 'oklch(0.32 0.06 75 / 0.3)', border: '1px solid oklch(0.50 0.13 75)', padding: '1px 6px', borderRadius: 4 }}>
              REVIEW
            </span>
          )}
          <StatusPill variant={statusVariant(inc)} />
        </div>
      </div>

      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {isAnalyzing && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {['Pulling SF field history…', 'Querying DB2 column…', 'Running hypothesis graph…'].map((line, i) => (
              <div key={i} style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--fg-3)', display: 'flex', gap: 6 }}>
                <span style={{ color: 'var(--info)' }}>›</span>{line}
              </div>
            ))}
          </div>
        )}

        {hypItems.length > 0 && <HypothesisPills hypotheses={hypItems} />}

        {inc.root_cause_summary && (
          <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-soft)', borderRadius: 6, padding: '8px 10px' }}>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--fg-3)', marginBottom: 4 }}>Root Cause</div>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 12.5, color: 'var(--fg-1)', lineHeight: 1.5 }}>{inc.root_cause_summary}</div>
          </div>
        )}

        {inc.evidence && inc.evidence.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {inc.evidence.slice(0, 3).map((ev, i) => (
              <EvidenceChip key={i} scheme={ev.source_type} description={ev.source_reference} />
            ))}
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 2 }}>
          <ConfidenceBar
            value={inc.confidence}
            status={isAnalyzing ? 'analyzing' : 'complete'}
            style={{ flex: 1 }}
          />
          <div style={{ display: 'flex', gap: 6 }}>
            {inc.id && (
              <button
                onClick={() => navigate(`/runs/${runId}/incidents/${inc.id}`)}
                style={{ padding: '4px 10px', borderRadius: 5, border: '1px solid var(--line)', background: 'var(--bg-2)', color: 'var(--fg-1)', fontFamily: 'var(--mono)', fontSize: 11, cursor: 'pointer' }}
              >
                Open Detail
              </button>
            )}
            <button
              onClick={() => navigate(`/runs/${runId}/summary`)}
              style={{ padding: '4px 10px', borderRadius: 5, border: '1px solid var(--line)', background: 'transparent', color: 'var(--fg-2)', fontFamily: 'var(--mono)', fontSize: 11, cursor: 'pointer' }}
            >
              View
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  )
}
