// Pure helpers for the incident views (unit-tested in src/lib/incident.test.ts).
import type { Evidence, HypothesisVerdictRecord, RCAIncident } from '@/types'

export const REVIEW_REASON_TEXT: Record<string, string> = {
  unknown_type: 'discrepancy type has no diagnosis path',
  no_hypothesis_confirmed: 'no hypothesis confirmed',
  graph_low_confidence: 'diagnosis rests on weak evidence',
  missing_evidence: 'a check produced no usable evidence',
  low_confidence: 'explanation confidence below 0.75',
  llm_unavailable: 'model unavailable',
  legacy_cache_flag: 'flagged by an older analysis',
  iteration_limit: 'analysis hit its step limit',
  critic_rejected: 'critic rejected a claim',
  critic_unavailable: 'critic could not review the explanation',
  proposer_invalid_output: 'model returned an invalid explanation',
}

export function reviewReasonText(reasons: string[] | undefined): string {
  if (!reasons || reasons.length === 0) return ''
  return 'Needs review: ' + reasons.map(r => REVIEW_REASON_TEXT[r] ?? r.replace(/_/g, ' ')).join('; ')
}

export interface TimelineStep {
  id: string
  label: string
  verdict: 'confirmed' | 'refuted' | 'inconclusive' | 'pending'
  reason: string
  tools: string[]
  evidence: Evidence[]
}

/** One step per tested hypothesis, in test order, with its recorded verdict and the tools that actually ran. */
export function timelineSteps(
  tested: string[],
  verdicts: HypothesisVerdictRecord[] | undefined,
  evidenceByHypothesis: Record<string, Evidence[]> | undefined,
): TimelineStep[] {
  const byId = new Map((verdicts ?? []).map(v => [v.hypothesis_id, v]))
  return tested.map(id => {
    const v = byId.get(id)
    const evidence = evidenceByHypothesis?.[id] ?? []
    const tools = [...new Set(evidence.map(e => e.tool).filter((t): t is string => !!t))]
    return {
      id,
      label: v?.label ?? id,
      verdict: v?.verdict ?? 'pending',
      reason: v?.reason ?? 'No verdict recorded for this step.',
      tools,
      evidence,
    }
  })
}

export function isUnconfirmed(inc: Pick<RCAIncident, 'graph_status'>): boolean {
  return inc.graph_status === 'exhausted' || inc.graph_status === 'unknown_type'
}

/** One line per incident for pasting into Jira: "[P1] Object.Field: summary (needs review)". */
export function jiraLines(
  incidents: { severity?: string | null; sf_object?: string | null; sf_field?: string | null;
    jira_summary?: string | null; root_cause_summary?: string | null; requires_human_review?: boolean }[],
): string {
  return incidents
    .map(i => {
      const where = [i.sf_object, i.sf_field].filter(Boolean).join('.') || 'unknown field'
      const text = (i.jira_summary || i.root_cause_summary || 'No summary').replace(/\s+/g, ' ').trim()
      return `[${i.severity ?? 'P?'}] ${where}: ${text}${i.requires_human_review ? ' (needs review)' : ''}`
    })
    .join('\n')
}

export function fmtUsd(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'n/a'
  return v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`
}

/** Pills for the live view: the recorded verdict per tested hypothesis (never inferred from ruled_out). */
export function hypothesisPills(
  tested: string[],
  verdicts: HypothesisVerdictRecord[] | undefined,
): { name: string; state: 'done' | 'fail' | 'inconclusive' | 'pending' }[] {
  const byId = new Map((verdicts ?? []).map(v => [v.hypothesis_id, v.verdict]))
  const STATE = { confirmed: 'done', refuted: 'fail', inconclusive: 'inconclusive' } as const
  return tested.map(name => {
    const v = byId.get(name)
    return { name, state: v ? STATE[v] : 'pending' }
  })
}
