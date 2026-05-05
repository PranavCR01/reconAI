import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { BrandMark } from '@/components/ui/BrandMark'

export interface TopBarProps {
  center?: ReactNode
  right?: ReactNode
}

export function TopBar({ center, right }: TopBarProps) {
  return (
    <header
      className="topbar-header"
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 20,
        height: 52,
        borderBottom: '1px solid var(--line)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 18px',
        gap: 18,
      }}
    >
      {/* Brand */}
      <Link
        to="/"
        style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', fontWeight: 600, letterSpacing: '-0.01em', flexShrink: 0 }}
      >
        <BrandMark />
        <span style={{ fontSize: 14 }}>
          <b style={{ color: 'var(--fg)' }}>reconAI</b>
          <span style={{ color: 'var(--fg-3)', margin: '0 4px' }}>/</span>
          <span style={{ color: 'var(--fg-2)', fontWeight: 500 }}>Reconciliation</span>
        </span>
      </Link>

      {/* Center (nav or breadcrumbs) */}
      {center}

      {/* Right — pushed to far end */}
      {right && (
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          {right}
        </div>
      )}
    </header>
  )
}

/* ---- Breadcrumbs ---- */
export interface Crumb { label: string; to?: string }

export function Breadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <nav style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--fg-2)', fontSize: 12.5, fontFamily: 'var(--mono)' }}>
      {crumbs.map((c, i) => (
        <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {i > 0 && <span style={{ color: 'var(--fg-3)' }}>›</span>}
          {c.to ? (
            <Link to={c.to} style={{ color: 'var(--fg-2)', textDecoration: 'none' }}>{c.label}</Link>
          ) : (
            <span style={{ color: 'var(--fg)', fontWeight: 500 }}>{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  )
}

/* ---- TopBadge (env / model indicator) ---- */
export function TopBadge({ dot, label, value }: { dot?: boolean; label?: string; value: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, height: 26, padding: '0 10px', borderRadius: 6, background: 'var(--bg-2)', border: '1px solid var(--line)', color: 'var(--fg-1)', fontSize: 12, fontFamily: 'var(--mono)', fontWeight: 500 }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--info)', boxShadow: '0 0 0 3px oklch(0.74 0.12 220 / 0.18)' }} />}
      {label && <span style={{ color: 'var(--fg-3)', fontWeight: 400 }}>{label}</span>}
      {value}
    </span>
  )
}
