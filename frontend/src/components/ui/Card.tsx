import type { ReactNode, CSSProperties } from 'react'

interface CardProps {
  children: ReactNode
  style?: CSSProperties
  className?: string
  padding?: number | string
  onClick?: () => void
}

export function Card({ children, style, className, padding = 16, onClick }: CardProps) {
  return (
    <div
      className={className}
      onClick={onClick}
      style={{
        background: 'var(--bg-1)',
        border: '1px solid var(--line-soft)',
        borderRadius: 8,
        padding,
        cursor: onClick ? 'pointer' : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  )
}
