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

describe('fixes from manual testing', () => {
  it('fix type defaults from the confirmed category', async () => {
    const { defaultFixType } = await import('./incident')
    expect(defaultFixType('FLS_STRIPPED')).toBe('fls_permission_grant')
    expect(defaultFixType('CDC_FIELD_EXCLUDED')).toBe('cdc_channel_config')
    expect(defaultFixType('DATAWAVE_TRANSFORM_ERROR')).toBe('dataweave_mapping_fix')
    expect(defaultFixType('APEX_SUPPRESSION')).toBe('apex_code_change')
    expect(defaultFixType(null)).toBe('other')
    expect(defaultFixType('SOMETHING_NEW')).toBe('other')
  })

  it('by-object groups by the real object, largest first', async () => {
    const { byObject } = await import('./incident')
    const groups = byObject([{ sf_object: 'Contact' }, { sf_object: 'Address__c' }, { sf_object: 'Contact' }, { sf_object: null }])
    expect(groups.map(([o, g]) => [o, g.length])).toEqual([['Contact', 2], ['Address__c', 1], ['unknown', 1]])
  })

  it('confidence is never reassuring on unconfirmed or escalated incidents', async () => {
    const { confidenceNeedsCaution, confidenceNote } = await import('./incident')
    expect(confidenceNeedsCaution({ graph_status: 'confirmed', judge_decision: 'accept' })).toBe(false)
    expect(confidenceNeedsCaution({ graph_status: 'exhausted', judge_decision: 'escalate' })).toBe(true)
    expect(confidenceNeedsCaution({ graph_status: 'confirmed', judge_decision: 'escalate' })).toBe(true)
    expect(confidenceNote({ graph_status: 'exhausted', judge_decision: 'escalate' })).toContain('not confirmed')
    expect(confidenceNote({ graph_status: 'confirmed', judge_decision: 'escalate' })).toContain('escalated')
  })
})
