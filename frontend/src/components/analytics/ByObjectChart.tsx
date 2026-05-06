import type { ByObjectRow } from '@/types'

interface Props {
  data: ByObjectRow[]
}

export function ByObjectChart({ data }: Props) {
  if (!data.length) return <div style={{ color: 'var(--fg-3)', font: '500 12px var(--mono)', padding: '16px 0' }}>No data</div>

  return (
    <div>
      {data.map((row) => {
        const total = row.total || 1
        const p1Pct = (row.p1 / total) * 100
        const p2Pct = (row.p2 / total) * 100
        const p3Pct = (row.p3 / total) * 100
        const displayName = row.object.replace('__c', '').replace('__C', '')

        return (
          <div
            key={row.object}
            style={{
              display: 'grid',
              gridTemplateColumns: '130px 1fr 70px',
              gap: 12,
              alignItems: 'center',
              padding: '8px 0',
              borderTop: '1px dashed var(--line-soft)',
            }}
          >
            <span style={{ font: '500 12.5px var(--mono)', color: 'var(--fg-1)' }}>
              {displayName}
            </span>
            <span style={{
              height: 18,
              background: 'var(--bg-2)',
              borderRadius: 3,
              display: 'flex',
              overflow: 'hidden',
              border: '1px solid var(--line-soft)',
            }}>
              <i style={{ width: `${p1Pct}%`, background: 'var(--p1)', display: 'block' }} />
              <i style={{ width: `${p2Pct}%`, background: 'var(--warn)', display: 'block' }} />
              <i style={{ width: `${p3Pct}%`, background: 'var(--p3)', display: 'block' }} />
            </span>
            <span style={{ font: '600 13px var(--mono)', color: 'var(--fg)', textAlign: 'right' }}>
              {row.total}
              <small style={{ color: 'var(--fg-3)', fontWeight: 500, fontSize: 10.5, display: 'block', marginTop: 1 }}>
                P1·{row.p1} P2·{row.p2} P3·{row.p3}
              </small>
            </span>
          </div>
        )
      })}

      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 10, paddingTop: 10, borderTop: '1px dashed var(--line-soft)' }}>
        {[
          { label: 'P1 critical', color: 'var(--p1)' },
          { label: 'P2 major', color: 'var(--warn)' },
          { label: 'P3 minor', color: 'var(--p3)' },
        ].map(({ label, color }) => (
          <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '500 11px var(--mono)', color: 'var(--fg-2)' }}>
            <i style={{ width: 10, height: 10, borderRadius: 2, background: color, display: 'block' }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}
