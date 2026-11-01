// Pure helpers for the incident views (unit-tested in src/lib/incident.test.ts).
import type { Evidence, FixType, HypothesisVerdictRecord, RCAIncident } from '@/types'

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

/** The resolution form's starting fix type, from the confirmed root-cause category. The analyst can change it. */
const FIX_FOR_CATEGORY: Record<string, FixType> = {
  FLS_STRIPPED: 'fls_permission_grant',
  CDC_FIELD_EXCLUDED: 'cdc_channel_config',
  DATAWAVE_TRANSFORM_ERROR: 'dataweave_mapping_fix',
  APEX_SUPPRESSION: 'apex_code_change',
  DELIVERY_GAP: 'replay_manual_trigger',
  DOWNSTREAM_OVERWRITE: 'data_backfill',
}

export function defaultFixType(category: string | null | undefined): FixType {
  return (category && FIX_FOR_CATEGORY[category]) || 'other'
}

/** Per-object rollup for the run summary (incidents carry sf_object from the run API). */
export function byObject<T extends { sf_object?: string | null }>(incidents: T[]): [string, T[]][] {
  const groups = new Map<string, T[]>()
  for (const inc of incidents) {
    const key = inc.sf_object || 'unknown'
    groups.set(key, [...(groups.get(key) ?? []), inc])
  }
  return [...groups.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
}

/** True when a confidence number should not be shown as reassuring (green). */
export function confidenceNeedsCaution(inc: Pick<RCAIncident, 'graph_status' | 'judge_decision'>): boolean {
  return isUnconfirmed(inc) || inc.judge_decision === 'escalate'
}

export function confidenceNote(inc: Pick<RCAIncident, 'graph_status' | 'judge_decision'>): string {
  if (isUnconfirmed(inc)) return 'diagnosis not confirmed · capped at 50%'
  if (inc.judge_decision === 'escalate') return 'explanation escalated to review'
  return 'model-stated confidence in the explanation'
}
