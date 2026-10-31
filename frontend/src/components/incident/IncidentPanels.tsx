import { useState } from 'react'
import { Panel } from '@/components/ui/Panel'
import { fmtUsd, isUnconfirmed, reviewReasonText, timelineSteps } from '@/lib/incident'
import type { Claim, Evidence, RCAIncident, SimilarIncidentDetail, TraceStep } from '@/types'

const mono = 'var(--mono)'
const VERDICT_STYLE = {
  confirmed: { icon: '✓', text: 'CONFIRMED', color: 'var(--ok)', bg: 'var(--ok-bg)' },
  refuted: { icon: '✕', text: 'REFUTED', color: 'var(--p1)', bg: 'var(--p1-bg)' },
  inconclusive: { icon: '?', text: 'INCONCLUSIVE', color: 'var(--warn)', bg: 'var(--p2-bg)' },
  pending: { icon: '·', text: 'NOT EVALUATED', color: 'var(--fg-3)', bg: 'var(--bg-2)' },
} as const

const OUTCOME_COLOR: Record<string, string> = {
  supports: 'var(--ok)', refutes: 'var(--p1)', neutral: 'var(--fg-2)', error: 'var(--warn)', skipped: 'var(--fg-3)',
}

const chip = (color: string): React.CSSProperties => ({
  fontFamily: mono, fontSize: 10, padding: '1px 6px', borderRadius: 4, color,
  border: '1px solid var(--line-soft)', background: 'var(--bg-2)', whiteSpace: 'nowrap',
})

const empty: React.CSSProperties = { fontFamily: mono, fontSize: 12, color: 'var(--fg-3)', textAlign: 'center', padding: '16px 0' }

// ---------------------------------------------------------------------------
export function UnconfirmedBanner({ inc }: { inc: Pick<RCAIncident, 'graph_status'> }) {
  if (!isUnconfirmed(inc)) return null
  return (
    <div role="alert" data-testid="unconfirmed-banner" style={{
      border: '1px solid var(--warn)', background: 'var(--p2-bg)', borderRadius: 8, padding: '10px 14px',
      color: 'var(--fg-1)', fontSize: 13, lineHeight: 1.5,
    }}>
      <b style={{ color: 'var(--warn)' }}>Unconfirmed.</b>{' '}
      No hypothesis was confirmed by evidence. The root cause below is the model's best guess from similar past
      incidents and was sent for human review.
    </div>
  )
}

export function ReviewReasons({ reasons }: { reasons?: string[] }) {
  const text = reviewReasonText(reasons)
  if (!text) return null
  return (
    <div data-testid="review-reasons" style={{ fontFamily: mono, fontSize: 12, color: 'var(--warn)', lineHeight: 1.5 }}>
      {text}
    </div>
  )
}

// ---------------------------------------------------------------------------
function EvidenceRow({ ev }: { ev: Evidence }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 6, padding: '8px 10px', minWidth: 0 }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={chip(OUTCOME_COLOR[ev.outcome ?? 'neutral'] ?? 'var(--fg-2)')}>{ev.outcome ?? 'neutral'}</span>
        {ev.tool && <span style={chip('var(--info)')}>{ev.tool}</span>}
        <span style={{ fontFamily: mono, fontSize: 10.5, color: 'var(--fg-3)', overflowWrap: 'anywhere' }}>{ev.source_reference}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--fg-1)', lineHeight: 1.5, marginTop: 6, overflowWrap: 'anywhere' }}>{ev.content}</div>
      {ev.raw_result && (
        <button onClick={() => setOpen(o => !o)} style={{ marginTop: 6, background: 'none', border: 'none', padding: 0,
          color: 'var(--info)', fontFamily: mono, fontSize: 10.5, cursor: 'pointer' }}>
          {open ? '▾ hide raw tool result' : '▸ raw tool result'}
        </button>
      )}
      {open && (
        <pre style={{ margin: '6px 0 0', fontFamily: mono, fontSize: 10.5, color: 'var(--fg-2)', background: 'var(--bg-1)',
          borderRadius: 4, padding: 8, overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
          {JSON.stringify(ev.raw_result, null, 2)}
        </pre>
      )}
    </div>
  )
}

export function HypothesisTimeline({ inc }: { inc: RCAIncident }) {
  const steps = timelineSteps(inc.hypotheses_tested, inc.hypothesis_verdicts, inc.evidence_by_hypothesis)
  return (
    <Panel title="Hypothesis Execution" meta={`${steps.length} tested${inc.graph_version ? ` · graph ${inc.graph_version}` : ''}`}>
      {steps.length === 0 && <div style={empty}>No hypotheses were tested</div>}
      {steps.map((s, i) => {
        const st = VERDICT_STYLE[s.verdict]
        return (
          <div key={s.id} data-testid="timeline-step" data-verdict={s.verdict}
            style={{ display: 'flex', gap: 12, paddingBottom: 16, position: 'relative' }}>
            {i < steps.length - 1 && <div style={{ position: 'absolute', left: 9, top: 20, bottom: 0, width: 1, background: 'var(--line-soft)' }} />}
            <div style={{ width: 20, height: 20, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center',
              background: st.bg, border: `1px solid ${st.color}`, zIndex: 1 }}>
              <span style={{ fontSize: 10, color: st.color }}>{st.icon}</span>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: mono, fontSize: 12, fontWeight: 600, color: 'var(--fg-1)' }}>{s.id}</span>
                <span style={{ fontSize: 12.5, color: 'var(--fg-1)' }}>{s.label}</span>
                <span style={{ ...chip(st.color), background: st.bg }}>{st.text}</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--fg-2)', marginTop: 4, lineHeight: 1.5, overflowWrap: 'anywhere' }}>{s.reason}</div>
              {s.evidence.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                  {s.evidence.map((ev, j) => <EvidenceRow key={ev.id ?? j} ev={ev} />)}
                </div>
              )}
              {s.evidence.length === 0 && (
                <div style={{ fontFamily: mono, fontSize: 11, color: 'var(--warn)', marginTop: 6 }}>No evidence recorded for this step</div>
              )}
            </div>
          </div>
        )
      })}
      {inc.contributing_factors && inc.contributing_factors.length > 0 && (
        <div style={{ fontFamily: mono, fontSize: 11, color: 'var(--fg-3)' }}>
          Contributing factors: {inc.contributing_factors.join(', ').replace(/_/g, ' ')}
        </div>
      )}
    </Panel>
  )
}

// ---------------------------------------------------------------------------
const CRITIC_COLOR = { supported: 'var(--ok)', unsupported: 'var(--warn)', contradicted: 'var(--p1)' } as const

export function CriticPanel({ inc }: { inc: RCAIncident }) {
  const claims: Claim[] = inc.claims ?? []
  if (claims.length === 0) return null
  const evidenceIndex = new Map((inc.evidence ?? []).map((e, i) => [e.id, `E${i + 1}`]))
  const decision = inc.judge_decision ?? '—'
  return (
    <Panel title="Explanation Review" meta={`judge: ${decision} · ${inc.revision_count ?? 0} revision(s)`}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {claims.map(c => {
          const verdict = c.critic?.verdict
          const rejected = verdict === 'unsupported' || verdict === 'contradicted'
          return (
            <div key={c.claim_id} data-testid="claim" data-verdict={verdict ?? 'none'}
              style={{ borderLeft: `2px solid ${verdict ? CRITIC_COLOR[verdict] : 'var(--line)'}`, paddingLeft: 10 }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginBottom: 3 }}>
                <span style={chip('var(--fg-2)')}>{c.kind.replace('_', ' ')}</span>
                {c.status === 'hypothesis' && <span style={chip('var(--warn)')}>hypothesis</span>}
                {verdict && <span style={chip(CRITIC_COLOR[verdict])}>{verdict}{c.critic?.stage ? ` · ${c.critic.stage}` : ''}</span>}
                {c.evidence_ids.map(id => (
                  <span key={id} style={chip('var(--info)')} title={id}>
                    {id.startsWith('UNKNOWN:') ? `${id.slice(8)} (missing)` : evidenceIndex.get(id) ?? 'evidence'}
                  </span>
                ))}
              </div>
              <div style={{ fontSize: 12.5, color: rejected ? 'var(--fg-3)' : 'var(--fg-1)', lineHeight: 1.5,
                textDecoration: rejected ? 'line-through' : 'none', overflowWrap: 'anywhere' }}>
                {c.text}
              </div>
              {rejected && c.critic?.reason && (
                <div data-testid="critic-reason" style={{ fontSize: 12, color: CRITIC_COLOR[verdict!], marginTop: 3 }}>
                  Critic: {c.critic.reason}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Panel>
  )
}

// ---------------------------------------------------------------------------
export function SimilarIncidents({ items, cited }: { items?: SimilarIncidentDetail[]; cited: Set<string> }) {
  if (!items || items.length === 0) return null
  return (
    <Panel title="Similar Past Incidents" meta={`${items.length} retrieved`}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map(s => (
          <div key={s.id} data-testid="similar" style={{ background: 'var(--bg-2)', borderRadius: 6, padding: '8px 10px',
            border: `1px solid ${cited.has(s.id) ? 'var(--info)' : 'var(--line)'}` }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginBottom: 4 }}>
              <span style={chip('var(--info)')}>{Math.round(s.similarity * 100)}% similar</span>
              {s.root_cause_category && <span style={chip('var(--fg-2)')}>{s.root_cause_category}</span>}
              {cited.has(s.id) && <span style={chip('var(--ok)')}>cited</span>}
              <span style={{ fontFamily: mono, fontSize: 10.5, color: 'var(--fg-3)', overflowWrap: 'anywhere' }}>{s.source}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--fg-2)', lineHeight: 1.5 }}>{s.summary}</div>
          </div>
        ))}
      </div>
    </Panel>
  )
}

// ---------------------------------------------------------------------------
export function TracePanel({ inc }: { inc: RCAIncident }) {
  const trace: TraceStep[] = inc.trace ?? []
  if (trace.length === 0) return null
  return (
    <Panel title="Trace" meta={`${trace.length} steps · ${fmtUsd(inc.cost_usd)}`}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: mono, fontSize: 11 }}>
          <thead>
            <tr style={{ color: 'var(--fg-3)', textAlign: 'left' }}>
              {['#', 'node', 'ms', 'model calls', 'detail'].map(h => <th key={h} style={{ padding: '4px 6px', fontWeight: 500 }}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {trace.map((s, i) => (
              <tr key={i} data-testid="trace-step" style={{ borderTop: '1px solid var(--line-soft)', color: 'var(--fg-1)', verticalAlign: 'top' }}>
                <td style={{ padding: '4px 6px', color: 'var(--fg-3)' }}>{i + 1}</td>
                <td style={{ padding: '4px 6px' }}>{s.node}</td>
                <td style={{ padding: '4px 6px' }}>{s.duration_ms}</td>
                <td style={{ padding: '4px 6px', whiteSpace: 'nowrap' }}>
                  {s.llm_calls.length === 0 ? '—' : s.llm_calls.map((c, j) => (
                    <div key={j} style={{ color: c.error ? 'var(--warn)' : 'var(--fg-1)' }}>
                      {c.model} · {c.input_tokens}/{c.output_tokens} tok · {c.latency_ms} ms{c.error ? ' · failed' : ''}
                    </div>
                  ))}
                </td>
                <td style={{ padding: '4px 6px', color: 'var(--fg-2)', overflowWrap: 'anywhere', minWidth: 160 }}>
                  {Object.entries(s.detail).filter(([, v]) => v !== null && v !== undefined)
                    .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`).join(' · ')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {inc.cost_warnings && inc.cost_warnings.length > 0 && (
        <div style={{ fontFamily: mono, fontSize: 11, color: 'var(--warn)', marginTop: 8 }}>{inc.cost_warnings.join('; ')}</div>
      )}
    </Panel>
  )
}
