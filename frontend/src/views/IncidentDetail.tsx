import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { TopBar, Breadcrumbs } from '@/components/layout/TopBar'
import { StatusPill } from '@/components/ui/StatusPill'
import { SeverityBadge } from '@/components/ui/Badge'
import { ConfidenceBar } from '@/components/ui/ConfidenceBar'
import { Panel } from '@/components/ui/Panel'
import { getIncident, resolveIncident } from '@/lib/api'
import { fmtDate, fmtLatency, fmtTokens, fmtConfidence } from '@/lib/format'
import type { RCAIncident, Evidence, FixType, ResolveRequest, Resolution } from '@/types'

const FIX_TYPES: FixType[] = [
  'apex_code_change',
  'dataweave_mapping_fix',
  'fls_permission_grant',
  'cdc_channel_config',
  'replay_manual_trigger',
  'middleware_restart',
  'data_backfill',
  'other',
]

function SkeletonBlock({ h = 16, w = '100%' }: { h?: number; w?: string | number }) {
  return (
    <div style={{
      height: h, width: w, borderRadius: 4,
      background: 'linear-gradient(90deg, var(--bg-2) 0%, var(--bg-3) 50%, var(--bg-2) 100%)',
      backgroundSize: '200% 100%',
      animation: 'shimmer 1.4s infinite',
    }} />
  )
}

function statusVariant(status: string): 'ok' | 'review' | 'analyzing' | 'queued' | 'fail' | 'default' {
  if (status === 'complete') return 'ok'
  if (status === 'needs_review') return 'review'
  if (status === 'escalated') return 'fail'
  if (status === 'running') return 'analyzing'
  return 'default'
}

function HypStep({ name, pass, index }: { name: string; pass: boolean; index: number }) {
  return (
    <div style={{ display: 'flex', gap: 12, paddingBottom: 16, position: 'relative' }}>
      {/* Timeline line */}
      <div style={{ position: 'absolute', left: 9, top: 20, bottom: 0, width: 1, background: 'var(--line-soft)' }} />
      <div style={{
        width: 20, height: 20, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center',
        background: pass ? 'var(--ok-bg)' : 'oklch(0.26 0.06 25 / 0.4)',
        border: `1px solid ${pass ? 'var(--ok)' : 'var(--p1)'}`,
        zIndex: 1,
      }}>
        <span style={{ fontSize: 10, color: pass ? 'var(--ok)' : 'var(--p1)' }}>{pass ? '✓' : '✕'}</span>
      </div>
      <div style={{ flex: 1, paddingTop: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 600, color: 'var(--fg-1)' }}>H{index + 1}: {name}</span>
          <span style={{
            fontFamily: 'var(--mono)', fontSize: 10, padding: '1px 6px', borderRadius: 4,
            color: pass ? 'var(--ok)' : 'var(--p1)',
            background: pass ? 'var(--ok-bg)' : 'oklch(0.26 0.06 25 / 0.3)',
            border: `1px solid ${pass ? 'var(--ok)' : 'oklch(0.45 0.12 25)'}`,
          }}>
            {pass ? 'CONFIRMED' : 'RULED OUT'}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
          {['schema_diff', 'fls_check', 'splunk_query'].map(tool => (
            <span key={tool} style={{
              fontFamily: 'var(--mono)', fontSize: 10.5, padding: '2px 8px', borderRadius: 4,
              background: 'var(--info-bg)', border: '1px solid var(--line-soft)', color: 'var(--info)',
            }}>{tool}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

function EvidenceCard({ ev }: { ev: Evidence }) {
  return (
    <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 6, padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, padding: '1px 6px', borderRadius: 4, background: 'var(--info-bg)', border: '1px solid var(--line-soft)', color: 'var(--info)' }}>
          {ev.source_type}
        </span>
      </div>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--fg-2)', wordBreak: 'break-all' }}>{ev.source_reference}</div>
      <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--fg-1)', lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
        {ev.content}
      </div>
      <div style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--fg-3)', fontStyle: 'italic' }}>{ev.relevance_explanation}</div>
    </div>
  )
}

function CollapsiblePanel({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 8, overflow: 'hidden' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'none', border: 'none', borderBottom: open ? '1px solid var(--line)' : 'none', cursor: 'pointer', textAlign: 'left' }}
      >
        <span style={{ fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--fg-2)', flex: 1 }}>{title}</span>
        <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{open ? '▾' : '▸'}</span>
      </button>
      {open && <div style={{ padding: 12 }}>{children}</div>}
    </div>
  )
}

export default function IncidentDetail() {
  const { runId, incidentId } = useParams<{ runId: string; incidentId: string }>()
  const [incident, setIncident] = useState<(RCAIncident & { evidence: Evidence[] }) | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [resolveSuccess, setResolveSuccess] = useState(false)
  const [resolvedAt, setResolvedAt] = useState<string | null>(null)
  const [editingResolution, setEditingResolution] = useState(false)

  // Resolution form state
  const [formRoot, setFormRoot] = useState('')
  const [formFix, setFormFix] = useState('')
  const [formFixType, setFormFixType] = useState<FixType>('apex_code_change')
  const [formAiCorrect, setFormAiCorrect] = useState(true)
  const [formResolvedBy, setFormResolvedBy] = useState('j.kowalski')
  const [formNotes, setFormNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!incidentId) return
    setLoading(true)
    getIncident(incidentId)
      .then(data => {
        setIncident(data)
        if (data.resolution) {
          setResolvedAt(data.resolution.resolved_at)
          setFormRoot(data.resolution.confirmed_root_cause)
          setFormFix(data.resolution.fix_applied)
          setFormFixType(data.resolution.fix_type)
          setFormAiCorrect(data.resolution.ai_was_correct ?? true)
          setFormResolvedBy(data.resolution.resolved_by)
          setFormNotes(data.resolution.correction_notes ?? '')
        } else {
          setFormRoot(data.root_cause_summary ?? '')
        }
        setLoading(false)
      })
      .catch(e => {
        setError(String(e))
        setLoading(false)
      })
  }, [incidentId])

  async function handleResolve(e: React.FormEvent) {
    e.preventDefault()
    if (!incidentId) return
    setSubmitting(true)
    try {
      const body: ResolveRequest = {
        confirmed_root_cause: formRoot,
        fix_type: formFixType,
        fix_applied: formFix || "",
        ai_was_correct: formAiCorrect,
        resolved_by: formResolvedBy,
        correction_notes: formNotes || "",
      }
      await resolveIncident(incidentId, body)
      const now = new Date().toISOString()
      const newResolution: Resolution = {
        id: null,
        incident_id: incidentId,
        confirmed_root_cause: formRoot,
        fix_applied: formFix,
        fix_type: formFixType,
        fix_verified: false,
        verification_recon_run_id: null,
        ai_was_correct: formAiCorrect,
        correction_notes: formNotes || null,
        resolved_by: formResolvedBy,
        resolved_at: now,
      }
      setIncident(prev => prev ? { ...prev, resolution: newResolution } : null)
      setResolveSuccess(true)
      setResolvedAt(now)
      setEditingResolution(false)
    } catch {
      // ignore
    } finally {
      setSubmitting(false)
    }
  }

  const fieldStyle: React.CSSProperties = {
    width: '100%', background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 6,
    color: 'var(--fg)', fontFamily: 'var(--sans)', fontSize: 13, padding: '8px 10px',
    boxSizing: 'border-box', resize: 'vertical',
  }
  const labelStyle: React.CSSProperties = {
    fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4, display: 'block',
  }

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
        <TopBar center={<Breadcrumbs crumbs={[{ label: 'Live Analysis', to: runId ? `/runs/${runId}` : '/' }, { label: '…' }]} />} />
        <div style={{ maxWidth: 1320, margin: '0 auto', padding: '18px 24px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <SkeletonBlock h={40} />
            <SkeletonBlock h={200} />
            <SkeletonBlock h={120} />
          </div>
        </div>
      </div>
    )
  }

  if (error || !incident) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
        <TopBar center={<Breadcrumbs crumbs={[{ label: 'Live Analysis', to: runId ? `/runs/${runId}` : '/' }, { label: 'Error' }]} />} />
        <div style={{ maxWidth: 1320, margin: '0 auto', padding: '40px 24px', textAlign: 'center', fontFamily: 'var(--mono)', color: 'var(--p1)' }}>
          {error ?? 'Incident not found'}
        </div>
      </div>
    )
  }

  const inc = incident
  const confidence = inc.confidence ?? 0
  const confPct = Math.round(Math.min(Math.max(confidence, 0), 1) * 100)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)' }}>
      <TopBar
        center={
          <Breadcrumbs crumbs={[
            { label: 'Live Analysis', to: runId ? `/runs/${runId}` : '/' },
            { label: inc.id?.slice(0, 8) ?? '…' },
          ]} />
        }
      />

      <div style={{ maxWidth: 1320, margin: '0 auto', padding: '18px 24px 80px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20, alignItems: 'start' }}>
          {/* LEFT COLUMN */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* Incident header */}
            <Panel title="Incident" bodyPadding={14}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
                <SeverityBadge severity={inc.severity} />
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-2)' }}>{inc.id ?? '—'}</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--info)' }}>SF → DB2</span>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)' }}>{inc.recon_row_id ?? '—'}</span>
                <StatusPill variant={statusVariant(inc.status)} style={{ marginLeft: 'auto' }} />
                <button style={{ padding: '4px 12px', borderRadius: 5, border: '1px solid var(--line)', background: 'var(--bg-2)', color: 'var(--fg-1)', fontFamily: 'var(--mono)', fontSize: 11, cursor: 'pointer' }}>
                  Export
                </button>
                <button style={{ padding: '4px 12px', borderRadius: 5, border: '1px solid var(--ok)', background: 'var(--ok-bg)', color: 'var(--ok)', fontFamily: 'var(--mono)', fontSize: 11, cursor: 'pointer' }}>
                  Apply Fix
                </button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1, background: 'var(--line)', borderRadius: 6, overflow: 'hidden' }}>
                {[
                  { label: 'SF Object.Field', value: 'Account.AnnualRevenue' },
                  { label: 'DB2 Table.Column', value: 'ACCT_FACT.ANNUAL_REV' },
                  { label: 'Integration', value: inc.llm_model ?? 'MuleSoft CDC' },
                ].map(cell => (
                  <div key={cell.label} style={{ background: 'var(--bg-2)', padding: '8px 10px' }}>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>{cell.label}</div>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-1)', fontWeight: 500 }}>{cell.value}</div>
                  </div>
                ))}
              </div>
            </Panel>

            {/* Hypothesis Execution */}
            <Panel title="Hypothesis Execution" meta={`${inc.hypotheses_tested.length} tested`}>
              <div style={{ paddingTop: 4 }}>
                {inc.hypotheses_tested.length === 0 && (
                  <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-3)', textAlign: 'center', padding: '20px 0' }}>No hypotheses recorded</div>
                )}
                {inc.hypotheses_tested.map((hyp, i) => (
                  <HypStep key={hyp} name={hyp} pass={!inc.hypotheses_ruled_out.includes(hyp)} index={i} />
                ))}
              </div>
            </Panel>

            {/* Evidence panel */}
            <Panel title="Evidence" meta={`${inc.evidence.length} sources`}>
              {inc.evidence.length === 0 ? (
                <div style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-3)', textAlign: 'center', padding: '20px 0' }}>No evidence attached</div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                  {inc.evidence.map((ev, i) => <EvidenceCard key={ev.id ?? i} ev={ev} />)}
                </div>
              )}
            </Panel>

            {/* Similar Incidents */}
            {inc.similar_incidents.length > 0 && (
              <Panel title="Similar Past Incidents" meta={`${inc.similar_incidents.length} found`}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
                  {inc.similar_incidents.map((sid, i) => (
                    <div key={sid} style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 6, padding: '10px 12px' }}>
                      <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-2)', marginBottom: 4 }}>{sid.slice(0, 20)}…</div>
                      <div style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--info)' }}>
                        similarity: {inc.similarity_scores[i] != null ? `${Math.round(inc.similarity_scores[i] * 100)}%` : '—'}
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>
            )}

            {/* Suggested Fix */}
            <CollapsiblePanel title="Suggested Fix">
              {inc.suggested_fix ? (
                <div style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--fg-1)', lineHeight: 1.6, marginBottom: 12 }}>
                  {inc.suggested_fix}
                </div>
              ) : (
                <div style={{ color: 'var(--fg-3)', fontFamily: 'var(--mono)', fontSize: 12 }}>No fix suggested</div>
              )}
              {inc.postmortem_draft && (
                <pre style={{ fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--fg-1)', background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 6, padding: 12, overflow: 'auto', whiteSpace: 'pre-wrap', margin: 0 }}>
                  {inc.postmortem_draft}
                </pre>
              )}
            </CollapsiblePanel>

            {/* Postmortem */}
            {inc.postmortem_draft && (
              <CollapsiblePanel title="Postmortem Draft">
                <dl style={{ display: 'grid', gridTemplateColumns: '140px 1fr', gap: '8px 12px', margin: 0 }}>
                  {[
                    { dt: 'Incident ID', dd: inc.id ?? '—' },
                    { dt: 'Status', dd: inc.status },
                    { dt: 'Confidence', dd: fmtConfidence(inc.confidence) },
                    { dt: 'Tool Calls', dd: inc.total_tool_calls },
                    { dt: 'Latency', dd: fmtLatency(inc.latency_ms) },
                    { dt: 'Created', dd: fmtDate(inc.created_at) },
                  ].map(({ dt, dd }) => (
                    <>
                      <dt key={`dt-${dt}`} style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--fg-3)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{dt}</dt>
                      <dd key={`dd-${dt}`} style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-1)', margin: 0 }}>{String(dd)}</dd>
                    </>
                  ))}
                </dl>
              </CollapsiblePanel>
            )}

            {/* Jira Summary */}
            {inc.jira_summary && (
              <Panel title="Jira Summary" titleRight={
                <button
                  onClick={() => navigator.clipboard.writeText(inc.jira_summary ?? '')}
                  style={{ padding: '2px 8px', borderRadius: 4, border: '1px solid var(--line)', background: 'var(--bg-2)', color: 'var(--fg-2)', fontFamily: 'var(--mono)', fontSize: 10, cursor: 'pointer' }}
                >
                  Copy
                </button>
              }>
                <pre style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-1)', background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 6, padding: 12, overflow: 'auto', whiteSpace: 'pre-wrap', margin: 0 }}>
                  {inc.jira_summary}
                </pre>
              </Panel>
            )}

            {/* Resolution form */}
            <Panel title="Resolve Incident">
              {(resolveSuccess || (inc.resolution && !editingResolution)) ? (
                <div style={{ padding: '16px 0' }}>
                  <div style={{ textAlign: 'center', fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--ok)', marginBottom: 12 }}>
                    ✓ Resolution already recorded
                  </div>
                  {inc.resolution && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--fg-2)', background: 'var(--bg-2)', borderRadius: 6, padding: '10px 12px' }}>
                      <div><span style={{ color: 'var(--fg-3)' }}>confirmed_root_cause: </span>{inc.resolution.confirmed_root_cause}</div>
                      <div><span style={{ color: 'var(--fg-3)' }}>fix_applied: </span>{inc.resolution.fix_applied}</div>
                      <div><span style={{ color: 'var(--fg-3)' }}>fix_type: </span>{inc.resolution.fix_type}</div>
                      <div><span style={{ color: 'var(--fg-3)' }}>resolved_by: </span>{inc.resolution.resolved_by}</div>
                      <div><span style={{ color: 'var(--fg-3)' }}>ai_correct: </span>{String(inc.resolution.ai_was_correct ?? '—')}</div>
                      {inc.resolution.correction_notes && (
                        <div><span style={{ color: 'var(--fg-3)' }}>correction_notes: </span>{inc.resolution.correction_notes}</div>
                      )}
                    </div>
                  )}
                  <button
                    onClick={() => {
                      const r = inc.resolution
                      if (!r) return
                      setFormRoot(r.confirmed_root_cause || '')
                      setFormFix(r.fix_applied || '')
                      setFormFixType(r.fix_type || 'apex_code_change')
                      setFormAiCorrect(r.ai_was_correct ?? true)
                      setFormResolvedBy(r.resolved_by || '')
                      setFormNotes(r.correction_notes || '')
                      setEditingResolution(true)
                    }}
                    style={{ marginTop: 10, padding: '5px 14px', borderRadius: 5, border: '1px solid var(--line)', background: 'var(--bg-2)', color: 'var(--fg-2)', fontFamily: 'var(--mono)', fontSize: 11, cursor: 'pointer' }}
                  >
                    Edit resolution
                  </button>
                </div>
              ) : (
                <form onSubmit={handleResolve} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div>
                    <label style={labelStyle}>Confirmed Root Cause</label>
                    <textarea style={{ ...fieldStyle, minHeight: 80 }} value={formRoot} onChange={e => setFormRoot(e.target.value)} required />
                  </div>
                  <div>
                    <label style={labelStyle}>Fix Type</label>
                    <select style={{ ...fieldStyle, resize: undefined }} value={formFixType} onChange={e => setFormFixType(e.target.value as FixType)}>
                      {FIX_TYPES.map(ft => <option key={ft} value={ft}>{ft.replace(/_/g, ' ')}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={labelStyle}>Fix Applied</label>
                    <textarea style={{ ...fieldStyle, minHeight: 80 }} value={formFix} onChange={e => setFormFix(e.target.value)} required />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <label style={{ ...labelStyle, margin: 0 }}>AI Was Correct</label>
                    <button
                      type="button"
                      onClick={() => setFormAiCorrect(v => !v)}
                      style={{
                        width: 44, height: 24, borderRadius: 12, border: 'none', cursor: 'pointer',
                        background: formAiCorrect ? 'var(--ok)' : 'var(--bg-3)',
                        position: 'relative', transition: 'background 0.2s',
                      }}
                    >
                      <span style={{
                        position: 'absolute', width: 18, height: 18, borderRadius: '50%', background: 'var(--fg)',
                        top: 3, left: formAiCorrect ? 23 : 3, transition: 'left 0.2s',
                      }} />
                    </button>
                  </div>
                  <div>
                    <label style={labelStyle}>Resolved By</label>
                    <input style={{ ...fieldStyle, resize: undefined }} value={formResolvedBy} onChange={e => setFormResolvedBy(e.target.value)} required />
                  </div>
                  <div>
                    <label style={labelStyle}>Correction Notes (optional)</label>
                    <textarea style={{ ...fieldStyle, minHeight: 60 }} value={formNotes} onChange={e => setFormNotes(e.target.value)} />
                  </div>
                  <button
                    type="submit"
                    disabled={submitting}
                    style={{ padding: '8px 20px', borderRadius: 6, border: 'none', background: 'var(--ok)', color: 'oklch(0.15 0 0)', fontFamily: 'var(--mono)', fontSize: 12, fontWeight: 600, cursor: submitting ? 'not-allowed' : 'pointer', opacity: submitting ? 0.6 : 1 }}
                  >
                    {submitting ? 'Submitting…' : 'Submit Resolution'}
                  </button>
                </form>
              )}
            </Panel>
          </div>

          {/* RIGHT RAIL */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, position: 'sticky', top: 68 }}>
            {/* Confidence panel */}
            <Panel title="Confidence">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'center', padding: '8px 0' }}>
                <div style={{ fontFamily: 'var(--mono)', fontSize: 52, fontWeight: 700, color: confPct >= 75 ? 'var(--ok)' : confPct >= 50 ? 'var(--warn)' : 'var(--p1)', lineHeight: 1 }}>
                  {fmtConfidence(inc.confidence)}
                </div>
                <ConfidenceBar value={inc.confidence} status="complete" style={{ width: '100%' }} />
                <div style={{ display: 'flex', gap: 16, fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--fg-3)' }}>
                  <span>prior: 0.65</span>
                  <span>likelihood: {fmtConfidence(inc.confidence)}</span>
                  <span>n=3</span>
                </div>
              </div>
            </Panel>

            {/* Quick Stats */}
            <Panel title="Quick Stats">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: 'var(--line)', borderRadius: 6, overflow: 'hidden' }}>
                {[
                  { label: 'Records Affected', value: '1' },
                  { label: 'Tool Calls', value: String(inc.total_tool_calls) },
                  { label: 'Time to RCA', value: inc.latency_ms > 0 ? fmtLatency(inc.latency_ms) : '—' },
                  { label: 'Tokens', value: fmtTokens(inc.total_tokens_used) },
                ].map(stat => (
                  <div key={stat.label} style={{ background: 'var(--bg-2)', padding: '10px 12px' }}>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{stat.label}</div>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 18, fontWeight: 700, color: 'var(--fg)' }}>{stat.value}</div>
                  </div>
                ))}
              </div>
            </Panel>

            {/* Activity */}
            <Panel title="Activity">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { label: 'AI opened incident', time: fmtDate(inc.created_at), color: 'var(--info)' },
                  { label: 'AI confirmed hypothesis', time: fmtDate(inc.created_at), color: 'var(--ok)' },
                  { label: 'You opened detail view', time: 'just now', color: 'var(--fg-3)' },
                  ...(resolvedAt ? [{ label: 'Resolution recorded', time: fmtDate(resolvedAt), color: 'var(--ok)' }] : []),
                ].map((item, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: item.color, marginTop: 4, flexShrink: 0 }} />
                    <div>
                      <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--fg-1)' }}>{item.label}</div>
                      <div style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--fg-3)' }}>{item.time}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  )
}
