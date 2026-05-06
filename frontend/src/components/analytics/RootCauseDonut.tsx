import { PieChart, Pie, Cell, Tooltip } from 'recharts'
import type { RootCauseRow } from '@/types'

interface Props {
  data: RootCauseRow[]
}

const DISC_COLORS: Record<string, string> = {
  NULL_DOWNSTREAM:      '#e06040',
  VALUE_MISMATCH:       '#c8a030',
  STALE_VALUE:          '#8060d8',
  MISSING_RECORD:       '#4090d8',
  DUPLICATE_DOWNSTREAM: '#30b0a8',
}
const FALLBACK_COLORS = ['#e06040', '#c8a030', '#8060d8', '#4090d8', '#30b0a8', '#a060d0']

function getColor(name: string, idx: number): string {
  return DISC_COLORS[name] ?? FALLBACK_COLORS[idx % FALLBACK_COLORS.length]
}

export function RootCauseDonut({ data }: Props) {
  const total = data.reduce((s, r) => s + r.count, 0)

  if (!data.length) return (
    <div style={{ color: 'var(--fg-3)', font: '500 12px var(--mono)', padding: '16px 0' }}>No data</div>
  )

  const pieData = data.map((r, i) => ({
    name: r.root_cause,
    value: r.count,
    pct: r.pct,
    color: getColor(r.root_cause, i),
  }))

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: 18, alignItems: 'center' }}>
      <div style={{ position: 'relative', width: 160, height: 160 }}>
        <PieChart width={160} height={160}>
          <Pie
            data={pieData}
            cx={75}
            cy={75}
            innerRadius={47}
            outerRadius={68}
            dataKey="value"
            startAngle={90}
            endAngle={-270}
            strokeWidth={0}
          >
            {pieData.map((entry, idx) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const d = payload[0].payload
              return (
                <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 8, padding: '8px 12px', font: '500 11.5px var(--mono)', color: 'var(--fg-1)' }}>
                  <div style={{ color: 'var(--fg-3)', marginBottom: 4 }}>{d.name}</div>
                  <div>{d.pct}% · {d.value.toLocaleString()} incidents</div>
                </div>
              )
            }}
          />
        </PieChart>
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -55%)', textAlign: 'center', pointerEvents: 'none' }}>
          <div style={{ font: '600 20px var(--mono)', color: 'var(--fg)', letterSpacing: '-0.02em', lineHeight: 1 }}>
            {total.toLocaleString()}
          </div>
          <div style={{ font: '500 9.5px var(--mono)', color: 'var(--fg-3)', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 3 }}>
            incidents
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
        {pieData.map((entry, idx) => (
          <div key={entry.name} style={{
            display: 'grid', gridTemplateColumns: '14px 1fr 50px 36px',
            gap: 8, alignItems: 'center',
            padding: '5px 0',
            font: '500 12px var(--mono)', color: 'var(--fg-1)',
            borderTop: idx === 0 ? undefined : '1px dashed var(--line-soft)',
          }}>
            <i style={{ width: 10, height: 10, borderRadius: 2, background: entry.color, display: 'block' }} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 11 }}>
              {entry.name}
            </span>
            <span style={{ color: 'var(--fg)', fontWeight: 600, textAlign: 'right' }}>{entry.pct}%</span>
            <span style={{ color: 'var(--fg-3)', fontWeight: 500, textAlign: 'right' }}>{entry.value.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
