interface StatCardProps {
  label: string
  value: string | number
  unit?: string
  delta?: number | string
  deltaDir?: 'up' | 'down' | 'neutral'
  sparkData?: number[]
  valueColor?: 'ok' | 'warn' | 'crit' | 'default'
  footer?: React.ReactNode
}

export function StatCard({ label, value, unit, delta, deltaDir, sparkData, valueColor = 'default', footer }: StatCardProps) {
  const numClass = valueColor === 'ok' ? 'ok' : valueColor === 'warn' ? 'warn' : valueColor === 'crit' ? 'crit' : ''
  const deltaClass = deltaDir === 'down' ? 'down' : deltaDir === 'up' ? 'up' : ''

  const maxSpark = sparkData ? Math.max(...sparkData, 1) : 1

  return (
    <div style={{ background: 'var(--bg-1)', padding: '14px 16px' }}>
      <div style={{ font: '500 10.5px var(--mono)', color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </div>

      {footer == null ? (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
          <span style={{ font: '600 22px var(--mono)', color: numClass === 'ok' ? 'var(--ok)' : numClass === 'warn' ? 'var(--warn)' : numClass === 'crit' ? 'var(--p1)' : 'var(--fg)', letterSpacing: '-0.02em', lineHeight: 1 }}>
            {value}
            {unit && <span style={{ fontSize: 13, color: 'var(--fg-3)' }}>{unit}</span>}
          </span>
          {delta != null && (
            <span style={{ font: '500 11px var(--mono)', color: deltaClass === 'up' ? 'var(--p1)' : deltaClass === 'down' ? 'var(--ok)' : 'var(--fg-3)' }}>
              {delta}
            </span>
          )}
        </div>
      ) : (
        <div style={{ marginTop: 6, font: '500 12px var(--mono)', color: 'var(--fg)' }}>
          {footer}
        </div>
      )}

      {sparkData && sparkData.length > 0 && (
        <div style={{ display: 'flex', gap: 1, alignItems: 'flex-end', height: 18, marginTop: 8 }}>
          {sparkData.map((v, i) => {
            const h = Math.max(8, (v / maxSpark) * 100)
            const opacity = 0.45 + (v / maxSpark) * 0.55
            return (
              <i
                key={i}
                style={{
                  flex: 1,
                  height: `${h}%`,
                  background: 'var(--bg-3)',
                  borderRadius: 1,
                  opacity,
                  display: 'block',
                }}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
