import type { CSSProperties } from 'react'
import type { Severity } from '@/types'

const SEVERITY_STYLES: Record<Severity, { color: string; bg: string; border: string }> = {
  P1: { color: 'oklch(0.92 0.10 25)', bg: 'var(--p1-bg)', border: '1px solid oklch(0.45 0.15 25)' },
  P2: { color: 'oklch(0.93 0.10 75)', bg: 'var(--p2-bg)', border: '1px solid oklch(0.50 0.13 75)' },
  P3: { color: 'var(--fg-1)',          bg: 'var(--p3-bg)', border: '1px solid var(--line)'         },
}

interface SeverityBadgeProps {
  severity: Severity | null | undefined
  size?: 'sm' | 'md'
  style?: CSSProperties
}

export function SeverityBadge({ severity, size = 'md', style }: SeverityBadgeProps) {
  if (!severity) return null
  const s = SEVERITY_STYLES[severity]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        height: size === 'sm' ? 18 : 20,
        padding: size === 'sm' ? '0 5px' : '0 7px',
        borderRadius: 4,
        fontFamily: 'var(--mono)',
        fontSize: size === 'sm' ? 10 : 10.5,
        fontWeight: 600,
        letterSpacing: '0.04em',
        color: s.color,
        background: s.bg,
        border: s.border,
        flexShrink: 0,
        ...style,
      }}
    >
      {severity}
    </span>
  )
}
