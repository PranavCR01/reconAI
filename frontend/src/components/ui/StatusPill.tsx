import type { CSSProperties } from 'react'

type PillVariant = 'ok' | 'review' | 'fail' | 'analyzing' | 'queued' | 'default'

const VARIANT: Record<PillVariant, { bg: string; color: string; border: string; dotBg: string; dotShadow?: string; label: string }> = {
  ok: {
    bg: 'oklch(0.30 0.07 155 / 0.5)',
    color: 'oklch(0.92 0.10 155)',
    border: 'oklch(0.40 0.10 155)',
    dotBg: 'var(--ok)',
    dotShadow: '0 0 0 3px oklch(0.74 0.16 155 / 0.18)',
    label: 'resolved',
  },
  review: {
    bg: 'oklch(0.32 0.06 75 / 0.5)',
    color: 'oklch(0.93 0.10 75)',
    border: 'oklch(0.50 0.13 75)',
    dotBg: 'var(--warn)',
    label: 'needs review',
  },
  fail: {
    bg: 'oklch(0.30 0.09 25 / 0.5)',
    color: 'oklch(0.92 0.10 25)',
    border: 'oklch(0.45 0.15 25)',
    dotBg: 'var(--p1)',
    label: 'escalated',
  },
  analyzing: {
    bg: 'oklch(0.32 0.06 75 / 0.5)',
    color: 'oklch(0.93 0.10 75)',
    border: 'oklch(0.50 0.13 75)',
    dotBg: 'var(--warn)',
    label: 'analyzing',
  },
  queued: {
    bg: 'var(--bg-2)',
    color: 'var(--fg-2)',
    border: 'var(--line)',
    dotBg: 'var(--fg-3)',
    label: 'queued',
  },
  default: {
    bg: 'var(--bg-2)',
    color: 'var(--fg-1)',
    border: 'var(--line)',
    dotBg: 'var(--fg-3)',
    label: '',
  },
}

interface StatusPillProps {
  variant: PillVariant
  label?: string
  style?: CSSProperties
}

export function StatusPill({ variant, label, style }: StatusPillProps) {
  const v = VARIANT[variant]
  const isAnalyzing = variant === 'analyzing'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        height: 22,
        padding: '0 8px',
        borderRadius: 4,
        font: '500 11px var(--mono)',
        fontFamily: 'var(--mono)',
        fontSize: 11,
        fontWeight: 500,
        background: v.bg,
        color: v.color,
        border: `1px solid ${v.border}`,
        flexShrink: 0,
        ...style,
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: v.dotBg,
          boxShadow: v.dotShadow,
          flexShrink: 0,
          animation: isAnalyzing ? 'blink-dot 1.2s ease-in-out infinite' : undefined,
        }}
      />
      {label ?? v.label}
    </span>
  )
}
