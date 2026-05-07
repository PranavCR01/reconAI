import { Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, Cell,
} from 'recharts'
import benchmarkData from '../data/benchmark_data.json'

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
}

/* Hex equivalents for Recharts — CSS vars do not resolve inside SVG */
const HEX = {
  bg1:  '#1e2130',
  line: '#2d3245',
  fg:   '#f4f5f8',
  fg2:  '#8c93a8',
  fg3:  '#5c6278',
}

const { configs, failure_patterns, meta, written } = benchmarkData

/* ── Data transforms ── */

function buildAccuracyRow(
  label: string,
  key: 'root_cause_accuracy' | 'human_review_accuracy' | 'avg_confidence',
): Record<string, number | string> {
  const row: Record<string, number | string> = { metric: label }
  for (const c of configs) row[c.name] = c[key]
  return row
}

const accuracyData = [
  buildAccuracyRow('Root Cause', 'root_cause_accuracy'),
  buildAccuracyRow('Human Review', 'human_review_accuracy'),
  buildAccuracyRow('Confidence', 'avg_confidence'),
]

const latencyData = configs.map((c) => ({
  name: c.name.replace('Groq Llama 3.3 70B', 'Groq Llama').replace('Claude Sonnet', 'Claude'),
  value: c.avg_latency_s,
  color: c.color,
}))

const costData = configs.map((c) => ({
  name: c.name.replace('Groq Llama 3.3 70B', 'Groq Llama').replace('Claude Sonnet', 'Claude'),
  value: +(c.cost_per_incident * 1000).toFixed(2),
  color: c.color,
}))

const reviewData = configs.map((c) => ({
  name: c.name.replace('Groq Llama 3.3 70B', 'Groq Llama').replace('Claude Sonnet', 'Claude'),
  pct: Math.round((c.needs_review_count / c.total) * 100),
  count: c.needs_review_count,
  total: c.total,
  color: c.color,
}))

const failureData = failure_patterns.map((fp) => ({
  name: fp.pattern,
  count: fp.incident_count,
  color: fp.color,
}))

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

export default function Benchmark() {
  return (
    <>
      <style>{`
        .bmk-section { padding: 72px 32px; }
        .bmk-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .bmk-three-col { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
        .bmk-four-col { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
        .bmk-finding-item { display: flex; gap: 10; align-items: flex-start; margin-bottom: 14px; }
        .bmk-fail-card {
          background: oklch(0.19 0.006 250);
          border: 1px solid oklch(0.30 0.008 250);
          border-radius: 10px; padding: 20px 22px;
        }
        @media (max-width: 768px) {
          .bmk-section { padding: 48px 20px !important; }
          .bmk-two-col { grid-template-columns: 1fr !important; }
          .bmk-three-col { grid-template-columns: 1fr !important; }
          .bmk-four-col { grid-template-columns: 1fr 1fr !important; }
        }
      `}</style>

      <div style={{
        background: C.bg, color: C.fg,
        fontFamily: 'var(--sans)', fontSize: 13, lineHeight: 1.5,
        WebkitFontSmoothing: 'antialiased', minHeight: '100vh',
      }}>

        {/* ── Nav ── */}
        <nav style={{
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

        {/* ── Hero header ── */}
        <section style={{
          padding: '56px 32px 48px',
          background: C.bg1,
          borderBottom: `1px solid ${C.line}`,
        }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>LLM Benchmark</SectionLabel>
            <h1 style={{
              margin: '16px 0 12px',
              fontSize: 40, fontWeight: 700, letterSpacing: '-0.025em',
              lineHeight: 1.1, color: C.fg,
            }}>
              Benchmark Results
            </h1>
            <p style={{ margin: '0 0 32px', fontSize: 16, color: C.fg2, maxWidth: 580, lineHeight: 1.65 }}>
              3 LLM configurations · 50 incidents · ground truth comparison
            </p>

            {/* Meta stat row */}
            <div className="bmk-four-col" style={{ maxWidth: 700 }}>
              {[
                { label: 'Incidents', value: String(meta.total_incidents) },
                { label: 'FSC Objects', value: String(meta.objects_covered) },
                { label: 'Discrepancy Types', value: String(meta.discrepancy_types) },
                { label: 'Ground Truth', value: 'Labeled' },
              ].map(({ label, value }) => (
                <div key={label} style={{
                  background: C.bg2, border: `1px solid ${C.line}`,
                  borderRadius: 8, padding: '12px 16px',
                }}>
                  <div style={{ font: `700 22px var(--mono)`, color: C.fg, letterSpacing: '-0.02em', lineHeight: 1, marginBottom: 6 }}>
                    {value}
                  </div>
                  <div style={{ font: `500 11px var(--mono)`, color: C.fg3, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Why We Benchmarked ── */}
        <section className="bmk-section" style={{ background: C.bg }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Motivation</SectionLabel>
            <h2 style={{ margin: '16px 0 16px', fontSize: 24, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              Why We Benchmarked
            </h2>
            <p style={{ margin: 0, fontSize: 15, color: C.fg2, maxWidth: 680, lineHeight: 1.75 }}>
              {written.why}
            </p>
          </div>
        </section>

        {/* ── Methodology ── */}
        <section className="bmk-section" style={{ background: C.bg1, borderTop: `1px solid ${C.line}`, borderBottom: `1px solid ${C.line}` }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Methodology</SectionLabel>
            <h2 style={{ margin: '16px 0 16px', fontSize: 24, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              How the test was run
            </h2>
            <p style={{ margin: '0 0 28px', fontSize: 15, color: C.fg2, maxWidth: 680, lineHeight: 1.75 }}>
              {written.methodology}
            </p>
            <div style={{
              display: 'inline-flex', flexWrap: 'wrap', gap: 8,
              font: `500 11.5px var(--mono)`, color: C.fg3,
            }}>
              {[
                'NULL_DOWNSTREAM', 'VALUE_MISMATCH', 'MISSING_RECORD',
                'STALE_VALUE', 'SCHEMA_DRIFT',
              ].map((t) => (
                <span key={t} style={{
                  padding: '4px 10px', borderRadius: 5,
                  background: C.bg2, border: `1px solid ${C.line}`,
                }}>
                  {t}
                </span>
              ))}
            </div>
            <div style={{ marginTop: 16, font: `400 12px var(--mono)`, color: C.fg3, lineHeight: 1.6 }}>
              Ground truth: {meta.ground_truth_method}
            </div>
          </div>
        </section>

        {/* ── Chart 1: 3-way accuracy comparison ── */}
        <section className="bmk-section" style={{ background: C.bg }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Accuracy</SectionLabel>
            <h2 style={{ margin: '16px 0 32px', fontSize: 24, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              3-way accuracy comparison
            </h2>
            <ChartCard title="Root cause accuracy · human review accuracy · avg confidence  (%)">
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={accuracyData} barCategoryGap="28%" barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke={HEX.line} vertical={false} />
                  <XAxis
                    dataKey="metric"
                    tick={{ fill: HEX.fg2, fontSize: 12 }}
                    axisLine={false} tickLine={false}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fill: HEX.fg2, fontSize: 11 }}
                    axisLine={false} tickLine={false}
                    tickFormatter={(v: number) => `${v}%`}
                  />
                  <Tooltip
                    {...tooltipBase}
                    formatter={(v: number | string, name: string) => [`${v}%`, name]}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 12, color: HEX.fg2, paddingTop: 16 }}
                  />
                  {configs.map((c) => (
                    <Bar key={c.name} dataKey={c.name} fill={c.color} radius={[3, 3, 0, 0]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </section>

        {/* ── Chart 2: Latency + Cost ── */}
        <section className="bmk-section" style={{ background: C.bg1, borderTop: `1px solid ${C.line}`, borderBottom: `1px solid ${C.line}` }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Performance &amp; Cost</SectionLabel>
            <h2 style={{ margin: '16px 0 32px', fontSize: 24, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              Latency vs cost per incident
            </h2>
            <div className="bmk-two-col">
              <ChartCard title="Avg latency per run (seconds)">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={latencyData} barCategoryGap="40%">
                    <CartesianGrid strokeDasharray="3 3" stroke={HEX.line} vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: HEX.fg2, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: HEX.fg2, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `${v}s`} />
                    <Tooltip
                      {...tooltipBase}
                      formatter={(v: number | string) => [`${v}s`, 'Avg latency']}
                    />
                    <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                      {latencyData.map((d) => (
                        <Cell key={d.name} fill={d.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Estimated cost per incident (millicents)">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={costData} barCategoryGap="40%">
                    <CartesianGrid strokeDasharray="3 3" stroke={HEX.line} vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: HEX.fg2, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: HEX.fg2, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v: number) => `${v}m¢`} />
                    <Tooltip
                      {...tooltipBase}
                      formatter={(v: number | string) => [`${v}m¢ ($${(Number(v) / 100000).toFixed(5)})`, 'Cost/incident']}
                    />
                    <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                      {costData.map((d) => (
                        <Cell key={d.name} fill={d.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <div style={{ font: `400 11px var(--mono)`, color: C.fg3, marginTop: 10 }}>
                  1 m¢ = $0.00001 · Groq is free-tier; cost reflects token throughput budget
                </div>
              </ChartCard>
            </div>
          </div>
        </section>

        {/* ── Key Findings ── */}
        <section className="bmk-section" style={{ background: C.bg }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Key Findings</SectionLabel>
            <h2 style={{ margin: '16px 0 28px', fontSize: 24, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              Headline conclusions
            </h2>
            <div style={{ maxWidth: 720 }}>
              {written.key_findings.map((finding, i) => (
                <div key={i} style={{
                  borderLeft: '2px solid var(--info)',
                  paddingLeft: '12px',
                  marginBottom: '12px',
                  color: 'var(--fg-1)',
                  fontSize: '14px',
                  lineHeight: '1.6',
                }}>
                  {finding}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Chart 3: Human review flagging ── */}
        <section className="bmk-section" style={{ background: C.bg1, borderTop: `1px solid ${C.line}`, borderBottom: `1px solid ${C.line}` }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Human Review</SectionLabel>
            <h2 style={{ margin: '16px 0 10px', fontSize: 24, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              Human review flagging rate
            </h2>
            <p style={{ margin: '0 0 28px', fontSize: 13.5, color: C.fg2, maxWidth: 580, lineHeight: 1.65 }}>
              Incidents where <code style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>requires_human_review = true</code> — measuring
              how well each config knows when to escalate, not just whether it answers.
            </p>
            <ChartCard title="% of incidents flagged for human review">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={reviewData} barCategoryGap="45%">
                  <CartesianGrid strokeDasharray="3 3" stroke={HEX.line} vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: HEX.fg2, fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis
                    domain={[0, 60]}
                    tick={{ fill: HEX.fg2, fontSize: 11 }}
                    axisLine={false} tickLine={false}
                    tickFormatter={(v: number) => `${v}%`}
                  />
                  <Tooltip
                    {...tooltipBase}
                    formatter={(v: number | string, _name: string, payload: { payload?: { count: number; total: number } }) => [
                      `${v}%  (${payload?.payload?.count ?? ''} / ${payload?.payload?.total ?? ''} incidents)`,
                      'Flagged for review',
                    ]}
                  />
                  <Bar dataKey="pct" radius={[3, 3, 0, 0]}>
                    {reviewData.map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        </section>

        {/* ── Chart 4 + Failure pattern cards ── */}
        <section className="bmk-section" style={{ background: C.bg }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Failure Patterns</SectionLabel>
            <h2 style={{ margin: '16px 0 10px', fontSize: 24, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              Where all three configs fail
            </h2>
            <p style={{ margin: '0 0 28px', fontSize: 13.5, color: C.fg2, maxWidth: 600, lineHeight: 1.65 }}>
              11 incidents across all configs share the same three failure modes —
              graph-level issues that are model-agnostic and high-leverage to fix.
            </p>

            <ChartCard title="Incidents affected per failure mode (shared across all configs)">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={failureData} barCategoryGap="40%">
                  <CartesianGrid strokeDasharray="3 3" stroke={HEX.line} vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: HEX.fg2, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fill: HEX.fg2, fontSize: 11 }}
                    axisLine={false} tickLine={false}
                    tickFormatter={(v: number) => `${v}`}
                  />
                  <Tooltip
                    {...tooltipBase}
                    formatter={(v: number | string) => [`${v} incidents`, 'Affected']}
                  />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                    {failureData.map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* Failure cards */}
            <div className="bmk-three-col" style={{ marginTop: 24 }}>
              {failure_patterns.map((fp) => (
                <div key={fp.pattern} className="bmk-fail-card">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: '50%',
                      background: fp.color, flexShrink: 0,
                    }} />
                    <span style={{ font: `600 13px var(--sans)`, color: C.fg }}>{fp.pattern}</span>
                  </div>
                  <div style={{
                    display: 'inline-block', marginBottom: 10,
                    font: `600 11px var(--mono)`, color: fp.color,
                    background: `${fp.color}18`, border: `1px solid ${fp.color}40`,
                    borderRadius: 4, padding: '2px 7px',
                  }}>
                    {fp.incident_count} incidents
                  </div>
                  <p style={{ margin: 0, fontSize: 13, color: C.fg2, lineHeight: 1.7 }}>
                    {fp.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Production recommendation ── */}
        <section className="bmk-section" style={{ background: C.bg1, borderTop: `1px solid ${C.line}`, borderBottom: `1px solid ${C.line}` }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <SectionLabel>Recommendation</SectionLabel>
            <h2 style={{ margin: '16px 0 16px', fontSize: 24, fontWeight: 700, letterSpacing: '-0.015em', color: C.fg }}>
              What this means for production
            </h2>
            <p style={{ margin: '0 0 28px', fontSize: 15, color: C.fg2, maxWidth: 680, lineHeight: 1.75 }}>
              {written.recommendation}
            </p>

            {/* Config recommendation table */}
            <div style={{
              background: C.bg2, border: `1px solid ${C.line}`,
              borderRadius: 10, overflow: 'hidden', maxWidth: 700,
            }}>
              {[
                { config: 'Claude Sonnet', color: '#22c55e', use: 'P1 incidents · KYC/financial fields · SCHEMA_DRIFT' },
                { config: 'Groq Llama 3.3 70B', color: '#a855f7', use: 'High-volume P3 NULL_DOWNSTREAM at scale' },
                { config: 'Hybrid (default)', color: '#3b82f6', use: 'General production — Groq classifies, Sonnet synthesizes' },
              ].map(({ config, color, use }, i, arr) => (
                <div
                  key={config}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 14,
                    padding: '14px 20px',
                    borderBottom: i < arr.length - 1 ? `1px solid ${C.line}` : 'none',
                  }}
                >
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                  <span style={{ font: `600 13px var(--mono)`, color: C.fg, minWidth: 180 }}>{config}</span>
                  <span style={{ fontSize: 13, color: C.fg2 }}>{use}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Conclusion ── */}
        <section className="bmk-section" style={{ background: C.bg }}>
          <div style={{ maxWidth: 960, margin: '0 auto' }}>
            <p style={{ margin: 0, fontSize: 14, color: C.fg3, maxWidth: 600, lineHeight: 1.75, fontFamily: 'var(--mono)' }}>
              {written.conclusion}
            </p>
          </div>
        </section>

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
