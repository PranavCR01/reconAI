import { Panel } from '@/components/ui/Panel'
import catalogue from '../data/hypothesis_catalogue.json'

// Generated from backend/graph/hypotheses.py by `python -m backend.graph.publish`;
// a backend test fails if this file and the code disagree.
interface HypothesisRow {
  order: number
  id: string
  label: string
  category: string
  tool: string
  checks: string
  confirmed_when: string
  confidence: number
  weak_evidence_confidence: number | null
  goes_to_review: boolean
}
interface DiscrepancyType { type: string; description: string; hypotheses: HypothesisRow[] }
interface Catalogue { graph_version: string; review_threshold: number; discrepancy_types: DiscrepancyType[] }

const data = catalogue as Catalogue
const mono = 'var(--mono)'

function ConfidenceCell({ h }: { h: HypothesisRow }) {
  const review = h.goes_to_review
  return (
    <span style={{ fontFamily: mono, fontSize: 12, color: review ? 'var(--warn)' : 'var(--fg-1)', whiteSpace: 'nowrap' }}>
      {h.confidence.toFixed(2)}{review ? ' → review' : ''}
      {h.weak_evidence_confidence !== null && (
        <span style={{ display: 'block', color: 'var(--warn)', fontSize: 11 }}>
          {h.weak_evidence_confidence.toFixed(2)} if 1 event → review
        </span>
      )}
    </span>
  )
}

export default function Hypotheses() {
  const threshold = data.review_threshold.toFixed(2)
  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '20px 16px 80px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontFamily: mono, fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          Hypothesis graph · version {data.graph_version}
        </div>
        <h1 style={{ margin: '8px 0 6px', fontSize: 26, fontWeight: 700, color: 'var(--fg)' }}>What gets checked, and in what order</h1>
        <p style={{ margin: 0, fontSize: 14, color: 'var(--fg-2)', lineHeight: 1.6, maxWidth: 760 }}>
          The decision tree, encoded as rules. Each mismatch type has a fixed list of possible causes. Each cause runs one
          check and one rule. There is no AI in this step: the same input always gives the same diagnosis.
        </p>
      </div>

      <Panel title="How it runs">
        <ul data-testid="graph-rules" style={{ margin: 0, paddingLeft: 18, fontSize: 13.5, color: 'var(--fg-1)', lineHeight: 1.7 }}>
          <li>Checks run top to bottom, and it <b>stops at the first confirmed cause</b>; later checks don't run.</li>
          <li>Each check ends <b>✓ confirmed</b>, <b>✕ refuted</b>, or <b>? inconclusive</b> (the tool failed). A failed check is never treated as refuted.</li>
          <li>A confirmed cause below <b>{threshold}</b> confidence goes to a person: the evidence behind it is weaker.</li>
          <li>If nothing is confirmed, the incident is marked <b>unconfirmed</b> and goes to a person; the explanation may only call its answer a guess.</li>
          <li>Configuration causes are checked before delivery: missed events are common noise, and checking delivery first lets that noise hide the real cause.</li>
        </ul>
      </Panel>

      {data.discrepancy_types.map(t => (
        <Panel key={t.type} title={t.type} meta={t.description}>
          <div style={{ overflowX: 'auto' }}>
            <table data-testid={`catalogue-${t.type}`} style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: 'left', color: 'var(--fg-3)', fontFamily: mono, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  {['#', 'ID', 'Hypothesis', 'Check', 'Confirmed when…', 'Confidence'].map(h => (
                    <th key={h} style={{ padding: '6px 8px', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {t.hypotheses.map(h => (
                  <tr key={h.id} data-testid="catalogue-row" style={{ borderTop: '1px solid var(--line-soft)', verticalAlign: 'top' }}>
                    <td style={{ padding: '8px', fontFamily: mono, color: 'var(--fg-3)' }}>{h.order}</td>
                    <td style={{ padding: '8px', fontFamily: mono, fontWeight: 600, color: 'var(--fg-1)' }}>{h.id}</td>
                    <td style={{ padding: '8px', color: 'var(--fg-1)', minWidth: 180 }}>{h.label}</td>
                    <td style={{ padding: '8px', color: 'var(--fg-2)', minWidth: 140 }}>
                      {h.checks}
                      <span style={{ display: 'block', fontFamily: mono, fontSize: 10.5, color: 'var(--fg-3)' }}>{h.tool}</span>
                    </td>
                    <td style={{ padding: '8px', color: 'var(--fg-2)', minWidth: 200 }}>{h.confirmed_when}</td>
                    <td style={{ padding: '8px' }}><ConfidenceCell h={h} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ))}

      <Panel title="Notes">
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.7 }}>
          <li>
            <b>IDs vs order:</b> the IDs come from the original decision tree (H1, H2, H3a…). The order was changed to check
            configuration before delivery, so H2 now runs last for missing values.
          </li>
          <li>
            <b>Confidences</b> are set by hand from how conclusive each check is (for example, proving an Apex trigger skipped one
            specific record needs the trigger code or debug logs, so it sits below the review line). They are not learned from data.
          </li>
          <li>
            <b>Tools are simulated</b> in this demo: Salesforce, DB2 and Splunk results come from simulators driven by a declared
            fault per record.
          </li>
        </ul>
      </Panel>
    </div>
  )
}
