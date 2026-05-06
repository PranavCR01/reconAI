import { useState } from 'react'
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

interface ActiveSegment {
  name: string
  pct: number
}

interface TooltipEntry {
  payload?: { name: string; value: number; pct: number; color: string }
}

function DonutTooltip({ active, payload }: { active?: boolean; payload?: TooltipEntry[] }) {
  if (!active || !payload?.length) return null
  const seg = payload[0].payload
  if (!seg) return null
  return (
    <div style={{
      background: '#1a1a2e',
      border: '1px solid #3a3a50',
      borderRadius: 8,
      padding: '7px 12px',
      boxShadow: '0 4px 14px rgba(0,0,0,0.55)',
      minWidth: 110,
    }}>
      <div style={{ color: '#8080a0', fontSize: 10, fontWeight: 500, marginBottom: 3 }}>
        {seg.name.replace(/_/g, ' ')}
      </div>
      <div style={{ color: '#e8e8f4', fontSize: 15, fontWeight: 700, lineHeight: 1 }}>
        {seg.pct}%
      </div>
      <div style={{ color: '#a0a0c0', fontSize: 10.5, marginTop: 2 }}>
        {seg.value.toLocaleString()} incidents
      </div>
    </div>
  )
}

export function RootCauseDonut({ data }: Props) {
  const [active, setActive] = useState<ActiveSegment | null>(null)
  const total = data.reduce((s, r) => s + r.count, 0)

  if (!data.length) return (
    <div style={{ color: '#808090', font: '500 12px var(--mono)', padding: '16px 0' }}>No data</div>
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
            onMouseEnter={(_, idx) => setActive({ name: pieData[idx].name, pct: pieData[idx].pct })}
            onMouseLeave={() => setActive(null)}
          >
            {pieData.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip content={<DonutTooltip />} />
        </PieChart>

        {/* Center label — static total or hover segment */}
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -55%)',
          textAlign: 'center', pointerEvents: 'none',
          transition: 'opacity 0.1s',
        }}>
          {active ? (
            <>
              <div style={{ font: '600 15px var(--mono)', color: '#d4d4e8', letterSpacing: '-0.01em', lineHeight: 1 }}>
                {active.pct}%
              </div>
              <div style={{ font: '500 9px var(--mono)', color: '#8080a0', letterSpacing: '0.04em', marginTop: 3, maxWidth: 70, lineHeight: 1.3 }}>
                {active.name.replace(/_/g, '_​')}
              </div>
            </>
          ) : (
            <>
              <div style={{ font: '600 20px var(--mono)', color: '#e8e8f4', letterSpacing: '-0.02em', lineHeight: 1 }}>
                {total.toLocaleString()}
              </div>
              <div style={{ font: '500 9.5px var(--mono)', color: '#8080a0', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 3 }}>
                incidents
              </div>
            </>
          )}
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
