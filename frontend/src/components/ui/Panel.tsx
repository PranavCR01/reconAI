import type { ReactNode, CSSProperties } from 'react'

interface PanelProps {
  title: string
  meta?: string
  children: ReactNode
  bodyPadding?: number | string
  style?: CSSProperties
  titleRight?: ReactNode
}

export function Panel({ title, meta, children, bodyPadding = 12, style, titleRight }: PanelProps) {
  return (
    <div
      style={{
        background: 'var(--bg-1)',
        border: '1px solid var(--line)',
        borderRadius: 8,
        overflow: 'hidden',
        ...style,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '10px 12px',
          borderBottom: '1px solid var(--line)',
          background: 'var(--bg-1)',
          gap: 10,
        }}
      >
        <span
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 11,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--fg-2)',
          }}
        >
          {title}
        </span>
        {titleRight}
        {meta && (
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--mono)',
              fontSize: 11,
              fontWeight: 500,
              color: 'var(--fg-3)',
            }}
          >
            {meta}
          </span>
        )}
      </div>
      <div style={{ padding: bodyPadding }}>{children}</div>
    </div>
  )
}
