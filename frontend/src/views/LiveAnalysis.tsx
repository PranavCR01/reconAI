import { useEffect, useRef, useState, useMemo } from 'react'
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
import { useReconStore } from '@/store/reconStore'
import { connectToRun } from '@/lib/sse'
import { fmtLatency, fmtTokens, fmtCurrency } from '@/lib/format'
import type { RCAIncident, SSEIncidentEvent, Severity } from '@/types'

const SEV_COLOR: Record<string, string> = {
  P1: 'var(--p1)',
  P2: 'var(--p2)',
  P3: 'var(--p3)',
}

function sseToIncident(e: SSEIncidentEvent): RCAIncident {
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
    status: e.root_cause_summary ? 'complete' : 'running',
    llm_model: e.llm_model,
    total_tool_calls: 0,
    total_tokens_used: 0,
    latency_ms: 0,
    created_at: null,
    severity: e.severity,
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
  const heatCells = useRef<number[]>(Array.from({ length: 80 }, () => Math.random()))

  useEffect(() => {
    const id = setInterval(() => setElapsed(Date.now() - startTime), 1000)
    return () => clearInterval(id)
  }, [startTime])

  useEffect(() => {
    if (!runId) return
    store.setRunId(runId)
    const cleanup = connectToRun(runId, {
      onIncident: (e) => {
        store.upsertIncident(sseToIncident(e))
        store.setSseConnected(true)
        store.setRunStatus('streaming')
      },
      onDone: () => {
        store.setRunStatus('complete')
        store.setSseConnected(false)
        navigate(`/runs/${runId}/summary`)
      },
      onError: () => {
        store.setSseConnected(false)
      },
    }, store.llmConfig)
    return cleanup
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  const allIncidents = store.getIncidentsSorted()
  const total = allIncidents.length
  const p1Count = allIncidents.filter(i => i.severity === 'P1').length
  const resolvedCount = allIncidents.filter(i => i.status === 'complete').length
  const needsReviewCount = allIncidents.filter(i => i.status === 'needs_review').length
  const analyzingCount = allIncidents.filter(i => i.status === 'running').length
  const avgLatencyMs = total > 0 ? allIncidents.reduce((s, i) => s + i.latency_ms, 0) / total : 0
  const totalTokens = allIncidents.reduce((s, i) => s + i.total_tokens_used, 0)
  const totalToolCalls = allIncidents.reduce((s, i) => s + i.total_tool_calls, 0)
  const approxSpend = totalTokens * 0.000003
  const elapsedSec = Math.floor(elapsed / 1000)
  const etaStr = total > 0 && analyzingCount > 0
    ? `~${Math.max(0, Math.round((analyzingCount * elapsedSec) / Math.max(resolvedCount, 1)))}s`
    : total > 0 ? 'Done' : '…'

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
            {store.sseConnected && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ok)' }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--ok)', animation: 'blink-dot 1.2s ease-in-out infinite' }} />
                LIVE
              </span>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 10px', background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 6 }}>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)' }}>
                {resolvedCount}/{total} analyzed
              </span>
              <div style={{ width: 80, height: 4, background: 'var(--bg-3)', borderRadius: 2, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: total > 0 ? `${Math.round((resolvedCount / total) * 100)}%` : '0%', background: 'var(--ok)', borderRadius: 2, transition: 'width 0.4s' }} />
              </div>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>ETA {etaStr}</span>
            </div>
          </div>
        }
      />

      {/* Stats bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', borderBottom: '1px solid var(--line)', background: 'var(--bg-1)' }}>
        <StatCell label="Discrepancies" value={total} />
        <StatCell label="P1 Critical" value={p1Count} color="var(--p1)" />
        <StatCell label="Resolved" value={resolvedCount} color="var(--ok)" />
        <StatCell label="Needs Review" value={needsReviewCount} color="var(--warn)" />
        <StatCell label="Analyzing" value={analyzingCount} />
        <StatCell label="Mean Time / Incident" value={avgLatencyMs > 0 ? fmtLatency(avgLatencyMs) : '—'} />
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
                { label: 'Tokens / incident', value: total > 0 ? fmtTokens(Math.round(totalTokens / total)) : '—' },
                { label: 'Tool calls', value: String(totalToolCalls) },
                { label: 'Cache hit %', value: '—' },
                { label: 'Approx. spend', value: fmtCurrency(approxSpend) },
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

          <Panel title="Discrepancy Heatmap">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(10, 1fr)', gap: 3 }}>
              {heatCells.current.map((heat, i) => {
                const bg = heat > 0.7
                  ? `oklch(0.55 0.22 25 / ${Math.max(0.15, heat)})`
                  : heat > 0.4
                  ? `oklch(0.60 0.18 75 / ${Math.max(0.15, heat)})`
                  : `oklch(0.55 0.10 220 / ${Math.max(0.08, heat)})`
                return <div key={i} style={{ width: '100%', paddingBottom: '100%', background: bg, borderRadius: 2 }} />
              })}
            </div>
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
                onClick={() => navigate(`/incidents/${inc.id}`)}
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
