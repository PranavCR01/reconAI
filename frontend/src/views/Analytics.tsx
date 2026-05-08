import { useState, useEffect } from 'react'
import type {
  AnalyticsSummary,
  IncidentsOverTimeResponse,
  ByObjectRow,
  RootCauseRow,
  AIAccuracyResponse,
  DeploymentCorrelation,
} from '@/types'
import {
  getAnalyticsSummary,
  getIncidentsOverTime,
  getByObject,
  getRootCauseDistribution,
  getDeploymentCorrelation,
  getAIAccuracy,
} from '@/lib/api'
import { StatCard } from '@/components/analytics/StatCard'
import { IncidentsOverTime } from '@/components/analytics/IncidentsOverTime'
import { RootCauseDonut } from '@/components/analytics/RootCauseDonut'
import { ByObjectChart } from '@/components/analytics/ByObjectChart'
import { AIAccuracyChart } from '@/components/analytics/AIAccuracyChart'
import { DeploymentTable } from '@/components/analytics/DeploymentTable'

type Days = 7 | 30 | 90

const SPARK_RUNS = [4,6,5,7,4,5,6,8,5,7,6,5,8,7,9,6,5,7,6,8,7,5,6,8,5,7,6,8,7,5]
const SPARK_INC  = [38,42,35,48,40,52,46,55,42,58,49,44,62,55,68,49,42,55,48,64,55,42,49,62,40,55,48,62,55,42]
const SPARK_RES  = [78,80,82,79,83,84,82,85,83,84,86,85,87,86,84,83,84,86,85,84,86,85,87,86,82,84,85,87,86,82]
const SPARK_CONF = [82,84,85,83,86,87,85,88,86,87,89,88,89,88,87,86,87,89,88,87,89,88,90,89,86,87,89,90,89,88]

function Panel({ title, meta, children, noPad = false }: { title: string; meta?: string; children: React.ReactNode; noPad?: boolean }) {
  return (
    <section style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 10, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', borderBottom: '1px solid var(--line)' }}>
        <span style={{ font: '600 11px var(--mono)', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--fg-2)' }}>{title}</span>
        {meta && <span style={{ marginLeft: 'auto', font: '500 11px var(--mono)', color: 'var(--fg-3)' }}>{meta}</span>}
      </div>
      <div style={noPad ? undefined : { padding: 16 }}>{children}</div>
    </section>
  )
}

const SKEL: React.CSSProperties = {
  background: 'var(--bg-2)',
  borderRadius: 6,
  animation: 'shimmer-pulse 1.4s ease-in-out infinite',
}

function SkeletonBlock({ h, w = '100%', mb = 0 }: { h: number; w?: string | number; mb?: number }) {
  return <div style={{ ...SKEL, height: h, width: w, marginBottom: mb }} />
}

function ChartSkeleton({ h = 200 }: { h?: number }) {
  return <SkeletonBlock h={h} />
}

function StatSkeleton() {
  return (
    <div style={{ padding: '16px 18px' }}>
      <SkeletonBlock h={10} w="55%" mb={10} />
      <SkeletonBlock h={28} w="65%" mb={8} />
      <SkeletonBlock h={8} w="40%" />
    </div>
  )
}

export default function Analytics() {
  const [days, setDays] = useState<Days>(30)
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [overTime, setOverTime] = useState<IncidentsOverTimeResponse | null>(null)
  const [byObject, setByObject] = useState<ByObjectRow[] | null>(null)
  const [rootCause, setRootCause] = useState<RootCauseRow[] | null>(null)
  const [accuracy, setAccuracy] = useState<AIAccuracyResponse | null>(null)
  const [deployCorr, setDeployCorr] = useState<DeploymentCorrelation[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  function fetchWithRetry<T>(fn: () => Promise<T>, retries = 2, delay = 3000): Promise<T> {
    return fn().catch((e) =>
      retries > 0
        ? new Promise(r => setTimeout(r, delay)).then(() => fetchWithRetry(fn, retries - 1, delay))
        : Promise.reject(e)
    )
  }

  useEffect(() => {
    setLoading(true)
    setError(null)
    const weeks = Math.ceil(days / 7)
    Promise.all([
      fetchWithRetry(() => getAnalyticsSummary(days)),
      fetchWithRetry(() => getIncidentsOverTime(days)),
      fetchWithRetry(() => getByObject(days)),
      fetchWithRetry(() => getRootCauseDistribution(days)),
      fetchWithRetry(() => getDeploymentCorrelation(days)),
      fetchWithRetry(() => getAIAccuracy(weeks)),
    ])
      .then(([s, ot, bo, rc, dc, ai]) => {
        setSummary(s)
        setOverTime(ot)
        setByObject(bo)
        setRootCause(rc)
        setDeployCorr(dc)
        setAccuracy(ai)
        setLoading(false)
      })
      .catch((e: Error) => {
        setError(e.message)
        setLoading(false)
      })
  }, [days])

  const totalDeploys = overTime?.deployments.length ?? summary?.deploy_correlations.total_deploys ?? 0
  const spikeCount = summary?.deploy_correlations.count ?? 0

  return (
    <div style={{ maxWidth: 1440, margin: '0 auto', padding: '18px 24px 80px' }}>

      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, marginBottom: 18, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600, letterSpacing: '-0.01em' }}>Analytics</h1>
          <div style={{ color: 'var(--fg-3)', fontSize: 12.5, fontFamily: 'var(--mono)', marginTop: 4 }}>
            historical trends · all runs · org-wide
          </div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            height: 30, padding: '0 12px', borderRadius: 7,
            background: 'var(--bg-2)', border: '1px solid var(--line)',
            color: 'var(--fg-1)', font: '500 12px var(--mono)', cursor: 'default',
          }}>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 4h12M4 8h8M6 12h4"/>
            </svg>
            env: PROD + UAT
          </span>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            height: 30, padding: '0 12px', borderRadius: 7,
            background: 'var(--bg-2)', border: '1px solid var(--line)',
            color: 'var(--fg-1)', font: '500 12px var(--mono)', cursor: 'default',
          }}>
            integrations: all (4)
          </span>
          <div style={{
            display: 'inline-flex', background: 'var(--bg-2)',
            border: '1px solid var(--line)', borderRadius: 7, padding: 2,
          }}>
            {([7, 30, 90] as Days[]).map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                style={{
                  background: days === d ? 'var(--bg-3)' : 'transparent',
                  border: 0, color: days === d ? 'var(--fg)' : 'var(--fg-2)',
                  font: '500 12px var(--mono)', padding: '5px 12px',
                  borderRadius: 5, cursor: 'pointer',
                  boxShadow: days === d ? '0 1px 0 oklch(0.34 0.008 250)' : undefined,
                }}
              >
                {d}d
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div style={{ background: 'var(--p1-bg)', border: '1px solid var(--p1)', borderRadius: 8, padding: '12px 16px', color: 'var(--p1)', font: '500 12px var(--mono)', marginBottom: 18 }}>
          Failed to load analytics: {error}
        </div>
      )}

      {/* Stats row */}
      <section style={{
        display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)',
        gap: 1, background: 'var(--line)',
        border: '1px solid var(--line)', borderRadius: 10,
        overflow: 'hidden', marginBottom: 18,
      }}>
        {loading ? (
          Array.from({ length: 6 }, (_, i) => (
            <div key={i} style={{ background: 'var(--bg-1)' }}><StatSkeleton /></div>
          ))
        ) : (
          <>
            <StatCard
              label={`Runs · ${days}d`}
              value={summary?.runs.count.toLocaleString() ?? '—'}
              delta={summary ? `${summary.runs.delta_pct > 0 ? '+' : ''}${summary.runs.delta_pct}%` : undefined}
              deltaDir={summary ? (summary.runs.delta_pct > 0 ? 'up' : 'down') : undefined}
              sparkData={SPARK_RUNS}
            />
            <StatCard
              label="Incidents triaged"
              value={summary?.incidents_triaged.count.toLocaleString() ?? '—'}
              delta={summary ? `${summary.incidents_triaged.delta_pct > 0 ? '+' : ''}${summary.incidents_triaged.delta_pct}%` : undefined}
              deltaDir={summary ? (summary.incidents_triaged.delta_pct > 0 ? 'up' : 'down') : undefined}
              sparkData={SPARK_INC}
            />
            <StatCard
              label="Avg resolution rate"
              value={summary?.avg_resolution_rate.pct ?? '—'}
              unit="%"
              delta={summary ? `${summary.avg_resolution_rate.delta_pt > 0 ? '+' : ''}${summary.avg_resolution_rate.delta_pt}pt` : undefined}
              deltaDir={summary ? (summary.avg_resolution_rate.delta_pt >= 0 ? 'down' : 'up') : undefined}
              valueColor="ok"
              sparkData={SPARK_RES}
            />
            <StatCard
              label="Avg confidence"
              value={summary?.avg_confidence.pct ?? '—'}
              unit="%"
              delta={summary ? `${summary.avg_confidence.delta_pt > 0 ? '+' : ''}${summary.avg_confidence.delta_pt}pt` : undefined}
              deltaDir={summary ? (summary.avg_confidence.delta_pt >= 0 ? 'down' : 'up') : undefined}
              sparkData={SPARK_CONF}
            />
            <StatCard
              label="Top root cause"
              value=""
              footer={summary ? (
                <>
                  {summary.top_root_cause.name}
                  <small style={{ color: 'var(--fg-3)', fontWeight: 500, display: 'block', marginTop: 2, fontSize: 10.5 }}>
                    {summary.top_root_cause.pct}% of incidents · {summary.top_root_cause.count.toLocaleString()} cases
                  </small>
                </>
              ) : <span style={{ color: 'var(--fg-3)' }}>—</span>}
            />
            <StatCard
              label="Deploy correlations"
              value={summary?.deploy_correlations.count ?? '—'}
              delta={summary ? `/ ${summary.deploy_correlations.total_deploys} deployments` : undefined}
              deltaDir="neutral"
              valueColor="warn"
              footer={undefined}
            />
          </>
        )}
      </section>

      {/* Main: incidents over time (70) + donut (30) */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 18, marginBottom: 18 }}>
        <Panel
          title="Incidents Over Time"
          meta={`last ${days}d · 5 categories · ${totalDeploys} deployments`}
        >
          {loading || !overTime ? <ChartSkeleton h={220} /> : <IncidentsOverTime data={overTime} />}
        </Panel>

        <Panel
          title="Root Cause Distribution"
          meta={`${days}d · n=${summary?.incidents_triaged.count.toLocaleString() ?? '…'}`}
        >
          {loading || !rootCause ? <ChartSkeleton h={160} /> : <RootCauseDonut data={rootCause} />}
        </Panel>
      </div>

      {/* Mid: by object (50) + AI accuracy (50) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, marginBottom: 18 }}>
        <Panel title={`By Object · ${days}d`} meta="P1 · P2 · P3 stacked">
          {loading || !byObject ? <ChartSkeleton h={200} /> : <ByObjectChart data={byObject} />}
        </Panel>

        <Panel title="AI Accuracy Trend" meta="recall@k · operator confirmation · weekly">
          {loading || !accuracy ? <ChartSkeleton h={200} /> : <AIAccuracyChart data={accuracy} />}
        </Panel>
      </div>

      {/* Full-width: deployment correlation */}
      <Panel
        title="Deployment Correlation"
        meta={`${totalDeploys} deployments · ${spikeCount} with ≥3σ incident spike +24h`}
        noPad
      >
        {loading || !deployCorr ? (
          <div style={{ padding: 16 }}><ChartSkeleton h={140} /></div>
        ) : (
          <DeploymentTable data={deployCorr} />
        )}
      </Panel>

    </div>
  )
}
