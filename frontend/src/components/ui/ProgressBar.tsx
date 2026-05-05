interface ProgressBarProps {
  value: number
  color?: string
  bg?: string
  height?: number
  showLabel?: boolean
}

export function ProgressBar({
  value,
  color,
  bg = 'var(--bg-3)',
  height = 4,
  showLabel = false,
}: ProgressBarProps) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100)
  const barColor = color ?? (pct >= 75 ? 'var(--ok)' : pct >= 50 ? 'var(--warn)' : 'var(--p1)')

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
      <div
        style={{
          flex: 1,
          height,
          background: bg,
          borderRadius: height / 2,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: barColor,
            borderRadius: height / 2,
            transition: 'width 0.3s ease',
          }}
        />
      </div>
      {showLabel && (
        <span
          style={{
            fontSize: 11,
            color: 'var(--fg-2)',
            fontFamily: 'var(--mono)',
            minWidth: 30,
            textAlign: 'right',
            flexShrink: 0,
          }}
        >
          {pct}%
        </span>
      )}
    </div>
  )
}
