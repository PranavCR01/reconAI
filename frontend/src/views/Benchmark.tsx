import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts'
import evalResults from '../data/eval_results.json'

/* ── Design-system colours ── */
const C = {
  bg:       'oklch(0.16 0.006 250)',
  bg1:      'oklch(0.19 0.006 250)',
  bg2:      'oklch(0.22 0.007 250)',
  bg3:      'oklch(0.26 0.008 250)',
  line:     'oklch(0.30 0.008 250)',
  fg:       'oklch(0.96 0.005 250)',
  fg1:      'oklch(0.82 0.006 250)',
  fg2:      'oklch(0.66 0.008 250)',
  fg3:      'oklch(0.50 0.008 250)',
  ok:       'oklch(0.74 0.16 155)',
  info:     'oklch(0.74 0.12 220)',
  violet:   'oklch(0.72 0.14 295)',
  warn:     'oklch(0.80 0.14 80)',
}

/* Hex equivalents for Recharts — CSS vars do not resolve inside SVG */
const HEX = {
  bg1:  '#1e2130',
  line: '#2d3245',
  fg:   '#f4f5f8',
  fg2:  '#8c93a8',
  fg3:  '#5c6278',
  ok:   '#22c55e',
  info: '#38bdf8',
  bad:  '#ef4444',
}

/* ── Eval results (generated: python -m backend.evals.run, then committed) ── */

type Rate = { k: number; n: number; rate: number | null; ci95: [number, number] | null }
type Ablation = { description: string; accuracy: Rate; review_rate: Rate; unsafe_auto_clear: Rate }
type PlantedEntry = {
  drafts: number
  critic_unavailable: number
  expected_stage?: string
  caught?: Rate
  caught_by_deterministic?: Rate
  caught_by_llm?: Rate
  false_rejection?: Rate
}
type Results = {
  mode: 'offline' | 'live'
  config: string
  models: string[]
  runs: number
  created_at: string
  git_sha: string | null
  source_file: string
  graph_version: string
  dataset: { incidents: number; sha256: string }
  caveats: string[]
  environment_notes: string[]
  metrics: {
    accuracy: { overall: Rate; by_discrepancy_type: Record<string, Rate> }
    efficiency: { within_min_hypotheses: Rate; mean_hypotheses_tested: number | null }
    routing: {
      unsafe_auto_clear: Rate
      review_rate: Rate
      review_vs_label: { precision: Rate; recall: Rate }
    }
    explanation: { judge_decisions: Record<string, number>; revised: Rate; grounded_when_accepted: Rate }
    consistency: Record<string, Rate> | null
    retrieval: { status: string; reason?: string }
    cost_latency: Record<string, number | null>
  }
  critic_planted: { incidents: number; by_draft: Record<string, PlantedEntry>; cost_usd: number | null }
  ablations: Record<string, Ablation> | null
  failure_patterns: { kind: string; detail: string; count: number; incidents: string[] }[]
}

const ALL = (evalResults as unknown as { results: Record<string, Results> }).results
const OFFLINE = ALL['offline_claude']
const LIVE = Object.entries(ALL).filter(([name]) => name.startsWith('live_')).map(([, r]) => r)

const pct = (r?: Rate | null) => (r && r.rate !== null ? `${Math.round(r.rate * 100)}%` : 'n/a')
const ci = (r?: Rate | null) =>
  r && r.ci95 ? `${r.k}/${r.n} · 95% CI ${Math.round(r.ci95[0] * 100)}–${Math.round(r.ci95[1] * 100)}%` : 'not measured'
const usd = (v: number | null | undefined) => (v === null || v === undefined ? 'n/a' : `$${v.toFixed(4)}`)
const secs = (v: number | null | undefined) => (v === null || v === undefined ? 'n/a' : `${(v / 1000).toFixed(1)} s`)

const byTypeData = Object.entries(OFFLINE.metrics.accuracy.by_discrepancy_type).map(([type, r]) => ({
  name: type.replace('_DOWNSTREAM', '').replace('_', ' '),
  accuracy: r.rate === null ? 0 : Math.round(r.rate * 100),
  n: r.n,
}))

const ablationData = Object.entries(OFFLINE.ablations ?? {}).map(([name, a]) => ({
  name: name.replace(/_/g, ' '),
  description: a.description,
  accuracy: a.accuracy.rate === null ? 0 : Math.round(a.accuracy.rate * 100),
  review: a.review_rate.rate === null ? 0 : Math.round(a.review_rate.rate * 100),
  unsafe: a.unsafe_auto_clear.rate === null ? 0 : Math.round(a.unsafe_auto_clear.rate * 100),
}))

const DEFECT_LABEL: Record<string, string> = {
  clean: 'Clean draft (should pass)',
  fabricated_evidence: 'Cites evidence that does not exist',
  fabricated_past_incident: 'Cites a past incident that does not exist',
  wrong_category: 'Names the wrong root-cause category',
  contradicts_refuted: 'Relies on a refuted hypothesis',
  placeholder_text: 'Contains template placeholders',
  unsupported_mechanism: 'Plausible mechanism no evidence supports',
}

/* ── Shared sub-components ── */

function LandingMark({ size = 24 }: { size?: number }) {
  return (
    <span style={{
      width: size, height: size, borderRadius: Math.round(size * 0.23),
      background: 'linear-gradient(135deg, oklch(0.55 0.14 250), oklch(0.42 0.12 295))',
      boxShadow: 'inset 0 0 0 1px oklch(0.70 0.10 250 / 0.3)',
      display: 'inline-grid', placeItems: 'center', position: 'relative', flexShrink: 0,
    }}>
      <span style={{
        position: 'absolute',
        inset: Math.round(size * 0.22),
        borderRadius: 2,
        border: '1.5px solid var(--fg)',
        borderRight: '1.5px solid transparent',
        borderBottom: '1.5px solid transparent',
        transform: 'rotate(45deg)',
      }} />
    </span>
  )
}

function SectionLabel({ children }: { children: string }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 10,
      font: `600 11px var(--mono)`,
      textTransform: 'uppercase', letterSpacing: '0.12em',
      color: C.fg3,
    }}>
      <span style={{ width: 3, height: 14, borderRadius: 2, background: C.info, flexShrink: 0 }} />
      {children}
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{
      background: C.bg1,
      border: `1px solid ${C.line}`,
      borderRadius: 12,
      padding: '24px 24px 16px',
    }}>
      <div style={{ font: `600 13px var(--sans)`, color: C.fg1, marginBottom: 20 }}>{title}</div>
      {children}
    </div>
  )
}

const tooltipBase = {
  contentStyle: {
    background: HEX.bg1, border: `1px solid ${HEX.line}`,
    borderRadius: 8, fontSize: 12, fontFamily: 'monospace',
  },
  labelStyle: { color: HEX.fg, marginBottom: 4 },
  itemStyle:  { color: HEX.fg2 },
}

/* ── Main view ── */

function Section({ label, title, alt, children }: { label: string; title: string; alt?: boolean; children: React.ReactNode }) {
  return (
    <section className="bmk-section" style={alt
      ? { background: C.bg1, borderTop: `1px solid ${C.line}`, borderBottom: `1px solid ${C.line}` }
      : { background: C.bg }}>
      <div style={{ maxWidth: 960, margin: '0 auto' }}>
        <SectionLabel>{label}</SectionLabel>
        <h2 style={{ margin: '16px 0 16px', fontSize: 24, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
          {title}
        </h2>
        {children}
      </div>
    </section>
  )
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ background: C.bg2, border: `1px solid ${C.line}`, borderRadius: 8, padding: '12px 16px', minWidth: 0 }}>
      <div style={{ font: `700 22px var(--mono)`, color: C.fg, letterSpacing: '-0.02em', lineHeight: 1, marginBottom: 6 }}>
        {value}
      </div>
      <div style={{ font: `500 11px var(--mono)`, color: C.fg3, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </div>
      {sub && <div style={{ font: `400 11px var(--mono)`, color: C.fg3, marginTop: 6, overflowWrap: 'anywhere' }}>{sub}</div>}
    </div>
  )
}

function Prose({ children }: { children: React.ReactNode }) {
  return <p style={{ margin: '0 0 24px', fontSize: 14.5, color: C.fg2, maxWidth: 700, lineHeight: 1.7 }}>{children}</p>
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div style={{ overflowX: 'auto', border: `1px solid ${C.line}`, borderRadius: 10 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} style={{ textAlign: 'left', padding: '10px 14px', color: C.fg3, font: `600 11px var(--mono)`,
                textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: `1px solid ${C.line}`, background: C.bg2 }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j} style={{ padding: '10px 14px', color: j === 0 ? C.fg1 : C.fg2, borderBottom: i < rows.length - 1 ? `1px solid ${C.line}` : 'none',
                  fontFamily: j === 0 ? 'var(--sans)' : 'var(--mono)', fontSize: j === 0 ? 13 : 12 }}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Benchmark() {
  const m = OFFLINE.metrics
  const planted = OFFLINE.critic_planted.by_draft
  const deterministicDefects = Object.entries(planted).filter(([k, e]) => k !== 'clean' && e.expected_stage === 'deterministic')
  const noisyOld = OFFLINE.ablations?.['delivery_first_all_confounders']
  const noisyNew = OFFLINE.ablations?.['all_confounders']
  const detCaught = deterministicDefects.reduce((s, [, e]) => s + (e.caught?.k ?? 0), 0)
  const detTotal = deterministicDefects.reduce((s, [, e]) => s + (e.caught?.n ?? 0), 0)

  return (
    <>
      <style>{`
        .bmk-section { padding: 64px 32px; }
        .bmk-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .bmk-four-col { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
        @media (max-width: 768px) {
          .bmk-section { padding: 44px 16px !important; }
          .bmk-two-col { grid-template-columns: 1fr !important; }
          .bmk-four-col { grid-template-columns: 1fr 1fr !important; }
          .bmk-nav { padding: 0 16px !important; }
        }
      `}</style>

      <div style={{
        background: C.bg, color: C.fg,
        fontFamily: 'var(--sans)', fontSize: 13, lineHeight: 1.5,
        WebkitFontSmoothing: 'antialiased', minHeight: '100vh', overflowX: 'hidden',
      }}>
        {/* ── Nav ── */}
        <nav className="bmk-nav" style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          height: 60, padding: '0 32px', flexShrink: 0,
          borderBottom: `1px solid ${C.line}`,
          background: C.bg1,
          position: 'sticky', top: 0, zIndex: 100,
        }}>
          <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
            <LandingMark size={22} />
            <span style={{ fontSize: 14, fontWeight: 600, color: C.fg }}>reconAI</span>
          </Link>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <Link
              to="/"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                height: 30, padding: '0 14px', borderRadius: 6,
                font: `500 12.5px var(--sans)`,
                background: 'transparent', border: `1px solid ${C.line}`,
                color: C.fg2, textDecoration: 'none',
              }}
            >
              ← Home
            </Link>
            <Link
              to="/upload"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                height: 30, padding: '0 14px', borderRadius: 6,
                font: `500 12.5px var(--sans)`,
                background: C.bg2, border: `1px solid ${C.line}`,
                color: C.fg1, textDecoration: 'none',
              }}
            >
              Open app →
            </Link>
          </div>
        </nav>

        {/* ── Hero ── */}
        <section style={{ padding: '56px 32px 48px', background: C.bg1, borderBottom: `1px solid ${C.line}` }} className="bmk-section">
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Evaluation</SectionLabel>
            <h1 style={{ margin: '16px 0 12px', fontSize: 40, fontWeight: 700, letterSpacing: '-0.025em', lineHeight: 1.1, color: C.fg }}>
              Eval results
            </h1>
            <p style={{ margin: '0 0 32px', fontSize: 16, color: C.fg2, maxWidth: 640, lineHeight: 1.65 }}>
              {OFFLINE.dataset.incidents} labeled incidents · hypothesis graph {OFFLINE.graph_version} · every number on
              this page comes from a committed results file and can be regenerated with one command.
            </p>
            <div className="bmk-four-col">
              <Tile label="Delivery-first + noise" value={pct(noisyOld?.accuracy)}
                sub={`accuracy vs ${pct(noisyNew?.accuracy)} as built (${noisyOld?.accuracy.k ?? '?'}/${noisyOld?.accuracy.n ?? '?'}): check order matters`} />
              <Tile label="Unsafe auto-clear" value={pct(m.routing.unsafe_auto_clear)} sub="wrong and not sent to review" />
              <Tile label="Critic: planted errors" value={detTotal ? `${Math.round((detCaught / detTotal) * 100)}%` : 'n/a'}
                sub={`${detCaught}/${detTotal} caught by deterministic checks`} />
              <Tile label="Live model run" value={LIVE.length ? 'measured' : 'pending'}
                sub={LIVE.length ? LIVE.map((r) => r.config).join(', ') : 'offline results only'} />
            </div>
          </div>
        </section>

        {/* ── Caveats ── */}
        <Section label="Read this first" title="What these numbers do and don't show">
          <div style={{ maxWidth: 720 }}>
            {OFFLINE.caveats.map((c) => (
              <div key={c} style={{ borderLeft: `2px solid ${C.warn}`, paddingLeft: 12, marginBottom: 12, color: C.fg1, fontSize: 14, lineHeight: 1.6 }}>
                {c}
              </div>
            ))}
          </div>
        </Section>

        {/* ── Diagnosis ── */}
        <Section label="Diagnosis" title="Hypothesis graph accuracy by discrepancy type" alt>
          <Prose>
            Graph accuracy is {pct(m.accuracy.overall)} ({ci(m.accuracy.overall)}). That is expected by construction:
            every simulated record contains its labeled fault, so this checks the logic, not real-world accuracy.
            The graph checks one hypothesis at a time and stops at the first confirmation. It needed{' '}
            {m.efficiency.mean_hypotheses_tested?.toFixed(2)} checks on average, and stayed within the labeled minimum
            path on {pct(m.efficiency.within_min_hypotheses)} of incidents. Small buckets have wide intervals.
          </Prose>
          <ChartCard title="Root-cause accuracy (%) · bar label = incidents in bucket">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={byTypeData} barCategoryGap="35%">
                <CartesianGrid strokeDasharray="3 3" stroke={HEX.line} vertical={false} />
                <XAxis dataKey="name" tick={{ fill: HEX.fg2, fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fill: HEX.fg2, fontSize: 11 }} axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `${v}%`} />
                <Tooltip {...tooltipBase} formatter={(v: number | string, _n: string, p: { payload?: { n: number } }) =>
                  [`${v}% of ${p?.payload?.n ?? ''}`, 'Accuracy']} />
                <Bar dataKey="accuracy" fill={HEX.ok} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </Section>

        {/* ── Ablations ── */}
        {ablationData.length > 0 && (
          <Section label="Ablations" title="Does the check order matter? Change it and see">
            <Prose>
              The same 50 incidents, re-run with the world or the graph changed. Confounders are seeded noise: an
              unrelated missed event (which looks like a delivery failure) and dormant Apex logic. Checking delivery
              first, as the pre-2.0 graph did, is what lets that noise win.
            </Prose>
            <ChartCard title="Accuracy vs share sent to human review (%)">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={ablationData} barCategoryGap="28%" barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke={HEX.line} vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: HEX.fg2, fontSize: 10 }} axisLine={false} tickLine={false} interval={0}
                    angle={-25} textAnchor="end" height={70} />
                  <YAxis domain={[0, 100]} tick={{ fill: HEX.fg2, fontSize: 11 }} axisLine={false} tickLine={false}
                    tickFormatter={(v: number) => `${v}%`} />
                  <Tooltip {...tooltipBase} formatter={(v: number | string, name: string) => [`${v}%`, name]} />
                  <Legend wrapperStyle={{ fontSize: 12, color: HEX.fg2, paddingTop: 12 }} />
                  <Bar dataKey="accuracy" name="Accuracy" fill={HEX.ok} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="review" name="Sent to review" fill={HEX.info} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="unsafe" name="Unsafe auto-clear" fill={HEX.bad} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <div style={{ marginTop: 16 }}>
              <Table head={['Variant', 'What changed']} rows={ablationData.map((a) => [a.name, a.description])} />
            </div>
          </Section>
        )}

        {/* ── Safety routing ── */}
        <Section label="Safety" title="When the system is wrong, does a person see it?" alt>
          <div className="bmk-four-col" style={{ marginBottom: 20 }}>
            <Tile label="Unsafe auto-clear" value={pct(m.routing.unsafe_auto_clear)} sub={ci(m.routing.unsafe_auto_clear)} />
            <Tile label="Sent to review" value={pct(m.routing.review_rate)} sub={ci(m.routing.review_rate)} />
            <Tile label="Review precision vs labels" value={pct(m.routing.review_vs_label.precision)} sub={ci(m.routing.review_vs_label.precision)} />
            <Tile label="Review recall vs labels" value={pct(m.routing.review_vs_label.recall)} sub={ci(m.routing.review_vs_label.recall)} />
          </div>
          <Prose>
            The review labels were written for an earlier design and assume some incidents are ambiguous. The simulated
            world makes most of them unambiguous, so the graph rarely asks for review and agreement with those labels
            is low. We report the disagreement rather than tune to it.
          </Prose>
        </Section>

        {/* ── Critic ── */}
        <Section label="Critic" title="Planted errors in RCA explanations">
          <Prose>
            For each confirmed incident we build a correct draft explanation, then copies with exactly one planted
            error, and run the real critic on each. Deterministic checks run first; the LLM critic only sees what they
            pass. The last row can only be caught by the LLM, so its offline number reflects a scripted critic.
          </Prose>
          <Table
            head={['Draft', 'Expected stage', 'Caught', 'Interval']}
            rows={Object.entries(planted).map(([kind, e]) => kind === 'clean'
              ? [DEFECT_LABEL[kind] ?? kind, '—', `${pct(e.false_rejection)} rejected`, ci(e.false_rejection)]
              : [DEFECT_LABEL[kind] ?? kind, e.expected_stage ?? '', pct(e.caught), ci(e.caught)])}
          />
        </Section>

        {/* ── Live ── */}
        <Section label="Live models" title="Real-model runs" alt>
          {LIVE.length === 0 ? (
            <Prose>
              No live run is committed yet, so explanation quality, the LLM critic, run-to-run consistency, cost and
              latency are not reported here. Run it with{' '}
              <code style={{ fontFamily: 'var(--mono)', fontSize: 12.5 }}>python -m backend.evals.run --mode live --config claude --runs 3 --yes</code>.
            </Prose>
          ) : LIVE.map((r) => {
            const cl = r.metrics.cost_latency
            const llmRow = r.critic_planted.by_draft['unsupported_mechanism']
            return (
              <div key={r.source_file} style={{ marginBottom: 28 }}>
                <div style={{ font: `600 13px var(--mono)`, color: C.fg1, marginBottom: 12 }}>
                  {r.config} · {r.models.join(', ')} · {r.runs} run(s) · {r.created_at.slice(0, 10)}
                </div>
                <div className="bmk-four-col">
                  <Tile label="Accuracy" value={pct(r.metrics.accuracy.overall)} sub={ci(r.metrics.accuracy.overall)} />
                  <Tile label="Accepted explanations" value={String(r.metrics.explanation.judge_decisions['accept'] ?? 0)}
                    sub={`grounded ${pct(r.metrics.explanation.grounded_when_accepted)}`} />
                  <Tile label="LLM critic catch" value={pct(llmRow?.caught)} sub={ci(llmRow?.caught)} />
                  <Tile label="Consistency" value={pct(r.metrics.consistency?.['judge_decision'])} sub="same judge decision across runs" />
                  <Tile label="Cost / incident" value={usd(cl['cost_usd_median'])} sub={`p95 ${usd(cl['cost_usd_p95'])}`} />
                  <Tile label="End-to-end" value={secs(cl['e2e_latency_ms_median'])} sub={`p95 ${secs(cl['e2e_latency_ms_p95'])}`} />
                  <Tile label="LLM time" value={secs(cl['llm_latency_ms_median'])} sub="median per incident" />
                  <Tile label="Retrieval" value={r.metrics.retrieval.status === 'measured' ? 'measured' : 'n/a'}
                    sub={r.metrics.retrieval.reason ?? ''} />
                </div>
              </div>
            )
          })}
        </Section>

        {/* ── Failures ── */}
        <Section label="Failures" title="Failure patterns">
          {[OFFLINE, ...LIVE].map((r) => (
            <div key={r.source_file} style={{ marginBottom: 16 }}>
              <div style={{ font: `600 12px var(--mono)`, color: C.fg3, marginBottom: 8 }}>{r.mode} / {r.config}</div>
              {r.failure_patterns.length === 0
                ? <div style={{ color: C.fg2, fontSize: 13.5 }}>None in this run.</div>
                : r.failure_patterns.map((f) => (
                  <div key={f.kind + f.detail} style={{ color: C.fg2, fontSize: 13.5, marginBottom: 6, overflowWrap: 'anywhere' }}>
                    <b style={{ color: C.fg1 }}>{f.kind}</b> ({f.detail}): {f.count} — {f.incidents.join(', ')}
                  </div>
                ))}
            </div>
          ))}
        </Section>

        {/* ── Reproduce ── */}
        <Section label="Reproduce" title="Regenerate these results" alt>
          <pre style={{ margin: 0, padding: 16, background: C.bg2, border: `1px solid ${C.line}`, borderRadius: 8,
            font: `400 12px var(--mono)`, color: C.fg1, overflowX: 'auto', whiteSpace: 'pre' }}>
{`python -m backend.evals.run --mode offline --config claude
python -m backend.evals.run --mode live --config claude --runs 3 --yes`}
          </pre>
          <div style={{ marginTop: 12, font: `400 12px var(--mono)`, color: C.fg3, overflowWrap: 'anywhere' }}>
            Source: {OFFLINE.source_file} · dataset sha256 {OFFLINE.dataset.sha256.slice(0, 12)}
            {OFFLINE.git_sha ? ` · commit ${OFFLINE.git_sha.slice(0, 7)}` : ''}
          </div>
        </Section>

        {/* ── Footer ── */}
        <footer style={{
          borderTop: `1px solid ${C.line}`,
          padding: '20px 32px',
          background: C.bg1,
          textAlign: 'center',
          font: `500 11px var(--mono)`,
          color: C.fg3,
          letterSpacing: '0.03em',
        }}>
          reconAI · LangGraph · Claude API · Supabase pgvector · UIUC 2026
        </footer>
      </div>
    </>
  )
}
