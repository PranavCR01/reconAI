import { describe, expect, it } from 'vitest'
import { fmtUsd, hypothesisPills, jiraLines, reviewReasonText, timelineSteps } from './incident'
import type { HypothesisVerdictRecord } from '@/types'

const v = (id: string, verdict: HypothesisVerdictRecord['verdict']): HypothesisVerdictRecord => ({
  hypothesis_id: id, label: id, kind: 'k', category: 'C', verdict, reason: 'r', confidence: null, evidence_ids: [],
})

describe('hypothesisPills', () => {
  it('uses recorded verdicts, not ruled_out', () => {
    expect(hypothesisPills(['HVM1', 'HVM2', 'HVM3'], [v('HVM1', 'refuted'), v('HVM2', 'inconclusive'), v('HVM3', 'confirmed')]))
      .toEqual([{ name: 'HVM1', state: 'fail' }, { name: 'HVM2', state: 'inconclusive' }, { name: 'HVM3', state: 'done' }])
  })
  it('legacy incidents without verdicts show pending, never confirmed', () => {
    expect(hypothesisPills(['H1', 'H2'], undefined).map(p => p.state)).toEqual(['pending', 'pending'])
  })
})

describe('timelineSteps', () => {
  it('keeps test order and de-duplicates tools', () => {
    const steps = timelineSteps(['B', 'A'], [v('A', 'confirmed'), v('B', 'refuted')], {
      B: [
        { id: '1', incident_id: null, source_type: 'splunk_log', source_reference: '', content: '', relevance_explanation: '', created_at: null, tool: 't1' },
        { id: '2', incident_id: null, source_type: 'splunk_log', source_reference: '', content: '', relevance_explanation: '', created_at: null, tool: 't1' },
      ],
    })
    expect(steps.map(s => [s.id, s.verdict, s.tools])).toEqual([['B', 'refuted', ['t1']], ['A', 'confirmed', []]])
  })
})

describe('jiraLines', () => {
  it('one line per incident, review flagged, whitespace collapsed', () => {
    expect(jiraLines([
      { severity: 'P1', sf_object: 'Contact', sf_field: 'Phone', jira_summary: 'FLS  stripped\nPhone', requires_human_review: false },
      { severity: 'P2', sf_object: 'Account', sf_field: null, jira_summary: null, root_cause_summary: 'Unknown', requires_human_review: true },
      { severity: null, sf_object: null, sf_field: null },
    ])).toBe(
      '[P1] Contact.Phone: FLS stripped Phone\n' +
      '[P2] Account: Unknown (needs review)\n' +
      '[P?] unknown field: No summary',
    )
  })
})

describe('formatting', () => {
  it('review reasons and cost', () => {
    expect(reviewReasonText([])).toBe('')
    expect(reviewReasonText(['some_new_reason'])).toBe('Needs review: some new reason')
    expect(fmtUsd(null)).toBe('n/a')
    expect(fmtUsd(0.0042)).toBe('$0.0042')
    expect(fmtUsd(0.052)).toBe('$0.052')
  })
})
