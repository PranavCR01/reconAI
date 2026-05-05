interface EvidenceChipProps {
  scheme: string
  description: string
  onClick?: () => void
}

export function EvidenceChip({ scheme, description, onClick }: EvidenceChipProps) {
  return (
    <span
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        height: 22,
        padding: '0 8px',
        borderRadius: 4,
        fontFamily: 'var(--mono)',
        fontSize: 11,
        fontWeight: 500,
        background: 'var(--bg-2)',
        border: '1px solid var(--line-soft)',
        color: 'var(--fg-1)',
        cursor: onClick ? 'pointer' : 'default',
        flexShrink: 0,
        maxWidth: 220,
        overflow: 'hidden',
        whiteSpace: 'nowrap',
        textOverflow: 'ellipsis',
      }}
    >
      <span style={{ color: 'var(--info)', flexShrink: 0 }}>{scheme}</span>
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{description}</span>
    </span>
  )
}
