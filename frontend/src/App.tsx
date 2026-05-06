import { BrowserRouter, Routes, Route, Navigate, useLocation, Link } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { Shell } from '@/components/layout/Shell'

const Landing = lazy(() => import('./views/Landing'))
const Upload = lazy(() => import('./views/Upload'))
const LiveAnalysis = lazy(() => import('./views/LiveAnalysis'))
const IncidentDetail = lazy(() => import('./views/IncidentDetail'))
const RunSummary = lazy(() => import('./views/RunSummary'))
const Analytics = lazy(() => import('./views/Analytics'))

function Loading() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        color: 'var(--fg-3)',
        fontFamily: 'var(--mono)',
        fontSize: '12px',
      }}
    >
      loading...
    </div>
  )
}

function AppNav() {
  const { pathname } = useLocation()
  const items = [
    { label: 'Runs', href: '/upload', matchPrefix: ['/upload', '/runs', '/incidents'] },
    { label: 'Analytics', href: '/analytics', matchPrefix: ['/analytics'] },
  ]
  return (
    <nav style={{ display: 'flex', gap: 2, marginLeft: 18 }}>
      {items.map(({ label, href, matchPrefix }) => {
        const active = matchPrefix.some((p) => pathname.startsWith(p))
        return (
          <Link
            key={label}
            to={href}
            style={{
              padding: '6px 12px',
              borderRadius: 6,
              color: active ? 'var(--fg)' : 'var(--fg-2)',
              textDecoration: 'none',
              fontSize: 13,
              fontWeight: 500,
              background: active ? 'var(--bg-2)' : 'transparent',
            }}
          >
            {label}
          </Link>
        )
      })}
    </nav>
  )
}

function AppRight() {
  return (
    <>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          height: 26,
          padding: '0 10px',
          borderRadius: 6,
          background: 'var(--bg-2)',
          border: '1px solid var(--line)',
          color: 'var(--fg-1)',
          fontSize: 12,
          fontFamily: 'var(--mono)',
          fontWeight: 500,
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: 'var(--ok)',
            boxShadow: '0 0 0 3px oklch(0.74 0.16 155 / 0.18)',
          }}
        />
        <span style={{ color: 'var(--fg-3)', fontWeight: 400 }}>org</span>
        td-bank-na
      </span>
      <button
        style={{
          width: 30,
          height: 30,
          display: 'grid',
          placeItems: 'center',
          borderRadius: 6,
          background: 'var(--bg-2)',
          border: '1px solid var(--line)',
          color: 'var(--fg-1)',
          cursor: 'pointer',
        }}
        title="Notifications"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M4 6a4 4 0 118 0v3l1 2H3l1-2V6z" />
          <path d="M6.5 13a1.5 1.5 0 003 0" />
        </svg>
      </button>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          height: 26,
          padding: '0 10px',
          borderRadius: 6,
          background: 'var(--bg-2)',
          border: '1px solid var(--line)',
          color: 'var(--fg-1)',
          fontSize: 12,
          fontFamily: 'var(--sans)',
          fontWeight: 500,
        }}
      >
        <span
          style={{
            width: 18,
            height: 18,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, oklch(0.6 0.12 295), oklch(0.5 0.10 250))',
            display: 'inline-grid',
            placeItems: 'center',
            fontSize: 9.5,
            fontWeight: 600,
            color: 'var(--fg)',
            flexShrink: 0,
          }}
        >
          JK
        </span>
        j.kowalski
      </span>
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell topBarCenter={<AppNav />} topBarRight={<AppRight />}>
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/runs/:runId" element={<LiveAnalysis />} />
            <Route path="/runs/:runId/summary" element={<RunSummary />} />
            <Route path="/runs/:runId/incidents/:incidentId" element={<IncidentDetail />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </BrowserRouter>
  )
}
