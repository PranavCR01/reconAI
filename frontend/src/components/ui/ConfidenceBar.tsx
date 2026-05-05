import type { CSSProperties } from 'react'

interface ConfidenceBarProps {
  value: number | null
  status?: 'queued' | 'analyzing' | 'complete'
  style?: CSSProperties
}

function getLevel(pct: number): 'high' | 'med' | 'low' {
  if (pct >= 75) return 'high'
  if (pct >= 50) return 'med'
  return 'low'
}

const FILL_GRADIENT: Record<'high' | 'med' | 'low', string> = {
  high: 'linear-gradient(90deg, var(--ok), oklch(0.80 0.14 155))',
  med:  'linear-gradient(90deg, var(--warn), oklch(0.82 0.13 75))',
  low:  'linear-gradient(90deg, var(--p1), oklch(0.72 0.18 25))',
}

export function ConfidenceBar({ value, status = 'complete', style }: ConfidenceBarProps) {
  const pct = value != null ? Math.round(Math.min(Math.max(value, 0), 1) * 100) : 0
  const level = getLevel(pct)
  const isQueued = status === 'queued'
  const isAnalyzing = status === 'analyzing'
  const label = isQueued ? '—' : isAnalyzing ? '…' : `${pct}%`

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 220, ...style }}>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 10.5, fontWeight: 500, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', flexShrink: 0 }}>
        Conf.
      </span>
      <div style={{ flex: 1, height: 4, background: 'var(--bg-3)', borderRadius: 2, overflow: 'hidden' }}>
        {!isQueued && !isAnalyzing && value != null && (
          <div style={{ width: `${pct}%`, height: '100%', borderRadius: 2, background: FILL_GRADIENT[level] }} />
        )}
      </div>
      <span style={{ fontFamily: 'var(--mono)', fontSize: 11.5, fontWeight: 500, color: isQueued || isAnalyzing ? 'var(--fg-3)' : 'var(--fg-1)', width: 38, textAlign: 'right', flexShrink: 0 }}>
        {label}
      </span>
    </div>
  )
}
