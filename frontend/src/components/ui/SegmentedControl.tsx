import type { ReactNode, CSSProperties } from 'react'

export interface SegOption {
  value: string
  label: ReactNode
  sub?: string
}

interface SegmentedControlProps {
  options: SegOption[]
  value: string
  onChange: (value: string) => void
  size?: 'sm' | 'lg'
  fullWidth?: boolean
  style?: CSSProperties
}

export function SegmentedControl({ options, value, onChange, size = 'sm', fullWidth, style }: SegmentedControlProps) {
  const isLg = size === 'lg'

  return (
    <div
      style={{
        display: 'inline-flex',
        background: 'var(--bg-2)',
        border: '1px solid var(--line)',
        borderRadius: isLg ? 8 : 6,
        padding: isLg ? 3 : 2,
        width: fullWidth ? '100%' : undefined,
        ...style,
      }}
    >
      {options.map((opt) => {
        const active = opt.value === value
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            style={{
              flex: fullWidth ? 1 : undefined,
              background: active ? 'var(--bg-3)' : 'transparent',
              border: 0,
              color: active ? 'var(--fg)' : 'var(--fg-2)',
              fontFamily: 'var(--sans)',
              fontSize: isLg ? 12.5 : 12,
              fontWeight: 500,
              padding: isLg ? '7px 12px' : '4px 10px',
              borderRadius: isLg ? 5 : 4,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              boxShadow: active
                ? isLg
                  ? '0 1px 0 oklch(0.35 0.008 250), inset 0 0 0 1px oklch(0.34 0.008 250)'
                  : '0 1px 0 oklch(0.35 0.008 250)'
                : undefined,
              whiteSpace: 'nowrap',
            }}
          >
            {opt.label}
            {opt.sub && (
              <span
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 10.5,
                  color: active ? 'var(--fg-2)' : 'var(--fg-3)',
                }}
              >
                {opt.sub}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
