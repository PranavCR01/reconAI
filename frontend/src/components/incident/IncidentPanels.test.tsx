import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CriticPanel, HypothesisTimeline, ReviewReasons, TracePanel, UnconfirmedBanner } from './IncidentPanels'
import { SigmaCell } from '@/components/analytics/DeploymentTable'
import type { Evidence, HypothesisVerdictRecord, RCAIncident } from '@/types'

afterEach(cleanup)

const ev = (id: string, hyp: string, tool: string, outcome: Evidence['outcome']): Evidence => ({
  id, incident_id: 'i', source_type: 'splunk_log', source_reference: `ref-${id}`, content: `content ${id}`,
  relevance_explanation: '', created_at: null, hypothesis_key: hyp, tool, outcome, raw_result: { status: 'ok', id },
})

const verdict = (id: string, v: HypothesisVerdictRecord['verdict']): HypothesisVerdictRecord => ({
  hypothesis_id: id, label: `label ${id}`, kind: 'k', category: 'C', verdict: v, reason: `reason ${id}`,
  confidence: v === 'confirmed' ? 0.9 : null, evidence_ids: [],
})

function incident(over: Partial<RCAIncident>): RCAIncident {
  return {
    id: 'inc-1', recon_row_id: 'row-1', hypotheses_tested: [], hypotheses_ruled_out: [], final_hypothesis: null,
    confidence: 0.9, similar_incidents: [], similarity_scores: [], root_cause_summary: 'x', suggested_fix: null,
    postmortem_draft: null, jira_summary: null, requires_human_review: false, status: 'complete', llm_model: null,
    total_tool_calls: 0, total_tokens_used: 0, latency_ms: 0, created_at: null, ...over,
  }
}

const verdictsShown = () => screen.getAllByTestId('timeline-step').map(s => s.getAttribute('data-verdict'))

describe('HypothesisTimeline', () => {
  it('confirmed at the third step: exactly one ✓, earlier steps keep their real verdicts', () => {
    const inc = incident({
      hypotheses_tested: ['H1', 'H3a', 'H3b'],
      hypotheses_ruled_out: ['H3a'],
      hypothesis_verdicts: [verdict('H1', 'inconclusive'), verdict('H3a', 'refuted'), verdict('H3b', 'confirmed')],
      evidence_by_hypothesis: {
        H1: [ev('e1', 'H1', 'get_db2_history', 'neutral')],
        H3a: [ev('e2', 'H3a', 'get_field_permissions', 'refutes')],
        H3b: [ev('e3', 'H3b', 'get_cdc_field_config', 'supports')],
      },
    })
    render(<HypothesisTimeline inc={inc} />)
    expect(verdictsShown()).toEqual(['inconclusive', 'refuted', 'confirmed'])
    expect(screen.getAllByText('CONFIRMED')).toHaveLength(1)
    // Real tools, no double "H1: H1" prefix, and the evidence is under its own step.
    expect(screen.getByText('get_cdc_field_config')).toBeTruthy()
    expect(screen.queryByText('schema_diff')).toBeNull()
    expect(screen.getByText('label H3b')).toBeTruthy()
    expect(screen.queryByText(/H\d+: H/)).toBeNull()
  })

  it('exhausted: every step refuted', () => {
    const inc = incident({
      graph_status: 'exhausted', hypotheses_tested: ['HSV1', 'HSV2'],
      hypothesis_verdicts: [verdict('HSV1', 'refuted'), verdict('HSV2', 'refuted')],
      evidence_by_hypothesis: { HSV1: [ev('a', 'HSV1', 't1', 'refutes')], HSV2: [ev('b', 'HSV2', 't2', 'refutes')] },
    })
    render(<HypothesisTimeline inc={inc} />)
    expect(verdictsShown()).toEqual(['refuted', 'refuted'])
    expect(screen.queryByText('CONFIRMED')).toBeNull()
  })

  it('a failed tool shows as inconclusive with its error evidence, never as refuted', () => {
    const inc = incident({
      hypotheses_tested: ['H2'], hypothesis_verdicts: [verdict('H2', 'inconclusive')],
      evidence_by_hypothesis: { H2: [ev('x', 'H2', 'splunk_query', 'error')] },
    })
    render(<HypothesisTimeline inc={inc} />)
    expect(verdictsShown()).toEqual(['inconclusive'])
    expect(screen.getByText('error')).toBeTruthy()
  })

  it('raw tool result expands on demand', () => {
    const inc = incident({
      hypotheses_tested: ['H2'], hypothesis_verdicts: [verdict('H2', 'refuted')],
      evidence_by_hypothesis: { H2: [ev('x', 'H2', 'splunk_query', 'refutes')] },
    })
    render(<HypothesisTimeline inc={inc} />)
    expect(screen.queryByText(/"status": "ok"/)).toBeNull()
    fireEvent.click(screen.getByText(/raw tool result/))
    expect(screen.getByText(/"status": "ok"/)).toBeTruthy()
  })
})

describe('UnconfirmedBanner', () => {
  it.each([
    ['exhausted', true], ['unknown_type', true], ['confirmed', false], [null, false],
  ] as const)('graph_status %s -> banner %s', (status, shown) => {
    render(<UnconfirmedBanner inc={{ graph_status: status }} />)
    expect(!!screen.queryByTestId('unconfirmed-banner')).toBe(shown)
  })
})

describe('CriticPanel', () => {
  it('strikes through rejected claims and shows the critic reason', () => {
    const inc = incident({
      judge_decision: 'escalate', revision_count: 1,
      evidence: [ev('e1', 'H1', 't', 'supports')],
      claims: [
        { claim_id: 'C1', kind: 'root_cause', status: 'established', category: 'FLS_STRIPPED', text: 'FLS stripped it',
          evidence_ids: ['e1'], similar_incident_ids: [], hypothesis_ids: ['H3a'],
          critic: { verdict: 'supported', reason: 'ok', stage: 'llm' } },
        { claim_id: 'C2', kind: 'mechanism', status: 'established', category: null, text: 'A purge job deleted it',
          evidence_ids: ['UNKNOWN:E9'], similar_incident_ids: [], hypothesis_ids: [],
          critic: { verdict: 'unsupported', reason: 'cites E9, which does not exist', stage: 'deterministic' } },
      ],
    })
    render(<CriticPanel inc={inc} />)
    const struck = screen.getByText('A purge job deleted it')
    expect(struck.style.textDecoration).toBe('line-through')
    expect(screen.getByText('FLS stripped it').style.textDecoration).toBe('none')
    expect(screen.getByTestId('critic-reason').textContent).toContain('cites E9, which does not exist')
    expect(screen.getByText('E9 (missing)')).toBeTruthy()
    expect(screen.getByText('E1')).toBeTruthy()
    expect(screen.getByText(/judge: escalate · 1 revision/)).toBeTruthy()
  })

  it('renders nothing without claims', () => {
    const { container } = render(<CriticPanel inc={incident({ claims: [] })} />)
    expect(container.innerHTML).toBe('')
  })
})

describe('ReviewReasons', () => {
  it('renders readable reasons', () => {
    render(<ReviewReasons reasons={['no_hypothesis_confirmed', 'critic_rejected']} />)
    expect(screen.getByTestId('review-reasons').textContent)
      .toBe('Needs review: no hypothesis confirmed; critic rejected a claim')
  })
  it('renders nothing for no reasons', () => {
    const { container } = render(<ReviewReasons reasons={[]} />)
    expect(container.innerHTML).toBe('')
  })
})

describe('TracePanel', () => {
  it('lists steps with model calls and cost', () => {
    const inc = incident({
      cost_usd: 0.0123,
      trace: [
        { node: 'ingestion', started_at: 't', duration_ms: 3, detail: { discrepancy_type: 'NULL_DOWNSTREAM' }, llm_calls: [] },
        { node: 'proposer', started_at: 't', duration_ms: 900, detail: { status: 'ok' },
          llm_calls: [{ agent: 'proposer', model: 'claude-sonnet-4-6', input_tokens: 1500, output_tokens: 400, latency_ms: 880 }] },
      ],
    })
    render(<TracePanel inc={inc} />)
    expect(screen.getAllByTestId('trace-step')).toHaveLength(2)
    expect(screen.getByText(/claude-sonnet-4-6 · 1500\/400 tok · 880 ms/)).toBeTruthy()
    expect(screen.getByText(/\$0\.012/)).toBeTruthy()
  })
})

describe('DeploymentTable SigmaCell', () => {
  it('shows the incident count, not sigma x 10', () => {
    render(<SigmaCell incidents={7} sigma={2.4} />)
    expect(screen.getByTestId('incidents-24h').textContent).toBe('7σ=2.4')
  })
})

describe('UnconfirmedBanner wording', () => {
  it('says the guess is unsupported when nothing similar was found', () => {
    render(<UnconfirmedBanner inc={{ graph_status: 'exhausted' }} similarCount={0} />)
    expect(screen.getByTestId('unconfirmed-banner').textContent).toContain('No similar past incidents were found')
  })
  it('names how many similar incidents informed the guess', () => {
    render(<UnconfirmedBanner inc={{ graph_status: 'exhausted' }} similarCount={3} />)
    expect(screen.getByTestId('unconfirmed-banner').textContent).toContain('informed by 3 similar past incidents')
  })
})

describe('ConfidenceBar caution', () => {
  it('a high value is not shown green when caution is set', async () => {
    const { ConfidenceBar } = await import('@/components/ui/ConfidenceBar')
    const { rerender } = render(<ConfidenceBar value={0.9} />)
    const level = () => screen.getByTestId('confidence-fill').dataset.level
    expect(level()).toBe('high')
    rerender(<ConfidenceBar value={0.9} caution />)
    expect(level()).toBe('med')
    rerender(<ConfidenceBar value={0.3} caution />)
    expect(level()).toBe('low')
  })
})
