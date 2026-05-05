import type { ReactNode, CSSProperties } from 'react'

interface TagProps {
  children: ReactNode
  color?: string
  bg?: string
  style?: CSSProperties
}

export function Tag({ children, color = 'var(--fg-2)', bg = 'var(--bg-2)', style }: TagProps) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '2px 6px',
        borderRadius: 4,
        fontSize: 11,
        fontFamily: 'var(--mono)',
        color,
        background: bg,
        border: '1px solid var(--line-soft)',
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {children}
    </span>
  )
}
