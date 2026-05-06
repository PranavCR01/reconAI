import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'
import type { IncidentsOverTimeResponse } from '@/types'

interface Props {
  data: IncidentsOverTimeResponse
}

const DISC_COLORS: Record<string, string> = {
  NULL_DOWNSTREAM:      '#e06040',
  VALUE_MISMATCH:       '#c8a030',
  STALE_VALUE:          '#8060d8',
  MISSING_RECORD:       '#4090d8',
  DUPLICATE_DOWNSTREAM: '#30b0a8',
}

const DISC_ORDER = ['NULL_DOWNSTREAM', 'VALUE_MISMATCH', 'STALE_VALUE', 'MISSING_RECORD', 'DUPLICATE_DOWNSTREAM']

export function IncidentsOverTime({ data }: Props) {
  const seriesKeys = DISC_ORDER.filter(k => data.series[k] !== undefined)

  const chartData = data.dates.map((date, i) => {
    const point: Record<string, number | string> = { date }
    for (const k of seriesKeys) {
      point[k] = data.series[k]?.[i] ?? 0
    }
    return point
  })

  const totals: Record<string, number> = {}
  for (const k of seriesKeys) {
    totals[k] = (data.series[k] ?? []).reduce((a, b) => a + b, 0)
  }

  const deployDates = new Set(data.deployments.map(d => d.date))

  const fmtDate = (iso: string) => {
    const d = new Date(iso + 'T00:00:00Z')
    return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 12 }}>
        {seriesKeys.map((k) => (
          <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '500 11px var(--mono)', color: 'var(--fg-2)' }}>
            <i style={{ width: 10, height: 3, borderRadius: 2, background: DISC_COLORS[k], display: 'block' }} />
            {k}
            <span style={{ color: 'var(--fg)', marginLeft: 4 }}>{totals[k]}</span>
          </span>
        ))}
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '500 11px var(--mono)', color: 'var(--fg-2)', marginLeft: 'auto' }}>
          <i style={{ width: 0, height: 12, borderLeft: '2px dashed oklch(0.82 0.006 250)', display: 'block' }} />
          deployment
        </span>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
          <CartesianGrid stroke="oklch(0.25 0.007 250)" strokeWidth={1} />
          <XAxis
            dataKey="date"
            tickFormatter={fmtDate}
            tick={{ fontFamily: 'var(--mono)', fontSize: 10.5, fill: 'oklch(0.50 0.008 250)' }}
            tickLine={false}
            axisLine={false}
            interval={Math.floor(data.dates.length / 6)}
          />
          <YAxis
            tick={{ fontFamily: 'var(--mono)', fontSize: 10.5, fill: 'oklch(0.50 0.008 250)' }}
            tickLine={false}
            axisLine={false}
            width={28}
          />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              const dep = data.deployments.find(d => d.date === label)
              const total = payload.reduce((s, p) => s + (typeof p.value === 'number' ? p.value : 0), 0)
              return (
                <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 8, padding: '10px 12px', boxShadow: '0 4px 18px oklch(0.05 0.005 250 / 0.6)', minWidth: 200, pointerEvents: 'none' }}>
                  <div style={{ font: '500 11px var(--mono)', color: 'var(--fg-3)', marginBottom: 6, paddingBottom: 6, borderBottom: '1px dashed var(--line)' }}>
                    {label}
                    {dep && <span style={{ color: 'var(--info)', marginLeft: 6 }}>deploy: {dep.name}</span>}
                  </div>
                  {payload.map((p) => (
                    <div key={p.dataKey as string} style={{ display: 'flex', alignItems: 'center', gap: 8, font: '500 11.5px var(--mono)', color: 'var(--fg-1)', padding: '2px 0' }}>
                      <i style={{ width: 8, height: 8, borderRadius: 2, background: p.color as string, display: 'block', flexShrink: 0 }} />
                      <span>{p.dataKey as string}</span>
                      <span style={{ marginLeft: 'auto', color: 'var(--fg)', fontWeight: 600 }}>{p.value as number}</span>
                    </div>
                  ))}
                  <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px dashed var(--line)', display: 'flex', justifyContent: 'space-between', font: '500 11px var(--mono)', color: 'var(--fg-3)' }}>
                    <span>total</span>
                    <b style={{ color: 'var(--fg)', fontWeight: 600 }}>{total}</b>
                  </div>
                </div>
              )
            }}
          />
          {data.deployments.map((dep) => (
            <ReferenceLine
              key={dep.date + dep.name}
              x={dep.date}
              stroke="oklch(0.82 0.006 250)"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
          ))}
          {seriesKeys.map((k) => (
            <Line
              key={k}
              type="monotone"
              dataKey={k}
              stroke={DISC_COLORS[k]}
              strokeWidth={1.6}
              dot={false}
              activeDot={{ r: 3.5, fill: DISC_COLORS[k], stroke: 'var(--bg)', strokeWidth: 2 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
