interface FieldMappingProps {
  sfObject: string
  sfField: string
  db2Table: string
  db2Column: string
  incidentId?: string
}

export function FieldMapping({ sfObject, sfField, db2Table, db2Column, incidentId }: FieldMappingProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        fontFamily: 'var(--mono)',
        fontSize: 12.5,
        background: 'var(--bg-2)',
        border: '1px solid var(--line-soft)',
        borderRadius: 6,
        padding: '8px 10px',
        gap: 10,
        overflow: 'hidden',
      }}
    >
      <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'oklch(0.74 0.10 220)', border: '1px solid oklch(0.40 0.06 220)', borderRadius: 3, padding: '1px 5px', flexShrink: 0 }}>SF</span>
        <span style={{ color: 'var(--fg)', fontWeight: 500 }}>{sfObject}</span>
        <span style={{ color: 'var(--fg-3)' }}>.</span>
        <span style={{ color: 'var(--info)' }}>{sfField}</span>
      </span>

      <span style={{ color: 'var(--fg-3)', flexShrink: 0 }}>→</span>

      <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <span style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'oklch(0.78 0.10 75)', border: '1px solid oklch(0.40 0.06 75)', borderRadius: 3, padding: '1px 5px', flexShrink: 0 }}>DB2</span>
        <span style={{ color: 'var(--fg)', fontWeight: 500 }}>{db2Table}</span>
        <span style={{ color: 'var(--fg-3)' }}>.</span>
        <span style={{ color: 'var(--info)' }}>{db2Column}</span>
      </span>

      {incidentId && (
        <span style={{ marginLeft: 'auto', color: 'var(--fg-3)', fontSize: 11, flexShrink: 0 }}>
          {incidentId}
        </span>
      )}
    </div>
  )
}
