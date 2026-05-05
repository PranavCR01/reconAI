interface SpinnerProps {
  size?: number
  color?: string
}

export function Spinner({ size = 16, color = 'var(--fg-3)' }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label="loading"
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        border: `2px solid ${color}`,
        borderTopColor: 'transparent',
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
        flexShrink: 0,
      }}
    />
  )
}
