import { BrowserRouter, Routes, Route, Navigate, useLocation, Link } from 'react-router-dom'
import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { Shell } from '@/components/layout/Shell'
import { trackPageView } from '@/lib/api'

const Landing = lazy(() => import('./views/Landing'))
const Upload = lazy(() => import('./views/Upload'))
const LiveAnalysis = lazy(() => import('./views/LiveAnalysis'))
const IncidentDetail = lazy(() => import('./views/IncidentDetail'))
const RunSummary = lazy(() => import('./views/RunSummary'))
const Analytics = lazy(() => import('./views/Analytics'))
const Benchmark = lazy(() => import('./views/Benchmark'))

const _API = (import.meta.env.VITE_API_URL as string | undefined) ?? '/api/v1'

function HealthBanner() {
  const [down, setDown] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const consecutiveFailures = useRef(0)

  useEffect(() => {
    async function check() {
      try {
        const res = await fetch(`${_API}/health`, { signal: AbortSignal.timeout(20000) })
        if (res.ok) {
          consecutiveFailures.current = 0
          setDown(false)
          setDismissed(false)
        } else {
          consecutiveFailures.current += 1
          if (consecutiveFailures.current >= 2) setDown(true)
        }
      } catch {
        consecutiveFailures.current += 1
        if (consecutiveFailures.current >= 2) setDown(true)
      }
    }
    const initialTimer = setTimeout(check, 10_000)
    const id = setInterval(check, 90_000)
    return () => { clearTimeout(initialTimer); clearInterval(id) }
  }, [])

  if (!down || dismissed) return null

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 9999,
      background: 'oklch(0.18 0.06 25)',
      borderBottom: '1px solid oklch(0.55 0.20 25)',
      padding: '9px 20px',
      display: 'flex', alignItems: 'center', gap: 10,
      fontFamily: 'var(--mono)', fontSize: 12,
      color: 'oklch(0.80 0.12 25)',
    }}>
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ flexShrink: 0 }}>
        <path d="M8 2L14.9 14H1.1L8 2z" /><path d="M8 7v3M8 12v.5" />
      </svg>
      ReconAI is temporarily unavailable. Our team has been notified.
      <button
        onClick={() => setDismissed(true)}
        style={{
          marginLeft: 'auto', background: 'none', border: 0,
          color: 'oklch(0.65 0.10 25)', cursor: 'pointer',
          fontFamily: 'var(--mono)', fontSize: 14, lineHeight: 1, padding: '0 4px',
        }}
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  )
}

function RouteTracker() {
  const { pathname } = useLocation()
  useEffect(() => {
    trackPageView(pathname)
  }, [pathname])
  return null
}

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
      <HealthBanner />
      <Shell topBarCenter={<AppNav />} topBarRight={<AppRight />}>
        <RouteTracker />
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/runs/:runId" element={<LiveAnalysis />} />
            <Route path="/runs/:runId/summary" element={<RunSummary />} />
            <Route path="/runs/:runId/incidents/:incidentId" element={<IncidentDetail />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/benchmark" element={<Benchmark />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </BrowserRouter>
  )
}
