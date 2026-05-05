import { forwardRef } from 'react'
import type { ButtonHTMLAttributes, ReactNode, CSSProperties } from 'react'

type Variant = 'primary' | 'ghost' | 'outline' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const VARIANT_STYLES: Record<Variant, CSSProperties> = {
  primary: { background: 'var(--info)',    color: 'oklch(0.96 0.005 250)' },
  ghost:   { background: 'transparent',    color: 'var(--fg-1)' },
  outline: { background: 'transparent',    color: 'var(--fg-1)', border: '1px solid var(--line)' },
  danger:  { background: 'var(--p1-bg)',   color: 'var(--p1)',   border: '1px solid oklch(0.65 0.20 25 / 0.3)' },
}

const SIZE_STYLES: Record<Size, CSSProperties> = {
  sm: { padding: '4px 10px', fontSize: 12 },
  md: { padding: '6px 14px', fontSize: 13 },
  lg: { padding: '8px 18px', fontSize: 14 },
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  children: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', loading, children, disabled, style, ...props }, ref) => {
    const inactive = disabled || loading
    return (
      <button
        ref={ref}
        disabled={inactive}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 6,
          border: 'none',
          borderRadius: 6,
          fontFamily: 'var(--sans)',
          fontWeight: 500,
          cursor: inactive ? 'not-allowed' : 'pointer',
          opacity: inactive ? 0.5 : 1,
          transition: 'opacity 0.12s',
          outline: 'none',
          whiteSpace: 'nowrap',
          lineHeight: 1.4,
          ...VARIANT_STYLES[variant],
          ...SIZE_STYLES[size],
          ...style,
        }}
        {...props}
      >
        {children}
      </button>
    )
  }
)
Button.displayName = 'Button'
