import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import type { AIAccuracyResponse } from '@/types'

interface Props {
  data: AIAccuracyResponse
}

const ACC_COLORS = {
  recall_at_1:    '#40b875',
  recall_at_3:    '#30b0a8',
  ai_was_correct: '#4090d8',
}

export function AIAccuracyChart({ data }: Props) {
  const chartData = data.weeks.map((week, i) => ({
    week,
    recall_at_1: data.recall_at_1[i],
    recall_at_3: data.recall_at_3[i],
    ai_was_correct: data.ai_was_correct[i],
  }))

  const { summary } = data

  return (
    <div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 12 }}>
        {[
          { key: 'recall_at_1', label: 'recall@1', val: summary.recall_at_1, color: ACC_COLORS.recall_at_1 },
          { key: 'recall_at_3', label: 'recall@3', val: summary.recall_at_3, color: ACC_COLORS.recall_at_3 },
          { key: 'ai_was_correct', label: 'ai_was_correct', val: summary.recall_at_1, color: ACC_COLORS.ai_was_correct },
        ].map(({ key, label, val, color }) => (
          <span key={key} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: '500 11px var(--mono)', color: 'var(--fg-2)' }}>
            <i style={{ width: 10, height: 3, borderRadius: 2, background: color, display: 'block' }} />
            {label}
            <span style={{ color: 'var(--fg)', marginLeft: 4 }}>
              {val > 0 ? `${val.toFixed(1)}%` : '—'}
            </span>
          </span>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ left: 0, right: 8, top: 8, bottom: 4 }}>
          <CartesianGrid stroke="oklch(0.25 0.007 250)" strokeWidth={1} />
          <XAxis
            dataKey="week"
            tick={{ fontFamily: 'var(--mono)', fontSize: 10.5, fill: 'oklch(0.50 0.008 250)' }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={[70, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tick={{ fontFamily: 'var(--mono)', fontSize: 10.5, fill: 'oklch(0.50 0.008 250)' }}
            tickLine={false}
            axisLine={false}
            width={38}
          />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              return (
                <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line)', borderRadius: 8, padding: '10px 12px', font: '500 11.5px var(--mono)', color: 'var(--fg-1)' }}>
                  <div style={{ color: 'var(--fg-3)', marginBottom: 6, paddingBottom: 6, borderBottom: '1px dashed var(--line)' }}>{label}</div>
                  {payload.map((p) => (
                    <div key={p.dataKey as string} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 0' }}>
                      <i style={{ width: 8, height: 8, borderRadius: 2, background: p.color as string, display: 'block', flexShrink: 0 }} />
                      <span>{p.dataKey as string}</span>
                      <span style={{ marginLeft: 'auto', color: 'var(--fg)', fontWeight: 600 }}>
                        {typeof p.value === 'number' ? `${p.value.toFixed(1)}%` : '—'}
                      </span>
                    </div>
                  ))}
                </div>
              )
            }}
          />
          <Line
            type="monotone"
            dataKey="recall_at_3"
            stroke={ACC_COLORS.recall_at_3}
            strokeWidth={1.7}
            dot={false}
            activeDot={{ r: 3, fill: ACC_COLORS.recall_at_3 }}
          />
          <Line
            type="monotone"
            dataKey="recall_at_1"
            stroke={ACC_COLORS.recall_at_1}
            strokeWidth={1.7}
            dot={false}
            activeDot={{ r: 3, fill: ACC_COLORS.recall_at_1 }}
          />
          <Line
            type="monotone"
            dataKey="ai_was_correct"
            stroke={ACC_COLORS.ai_was_correct}
            strokeWidth={1.7}
            strokeDasharray="3 3"
            dot={false}
            activeDot={{ r: 3, fill: ACC_COLORS.ai_was_correct }}
          />
        </LineChart>
      </ResponsiveContainer>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginTop: 14, paddingTop: 14, borderTop: '1px dashed var(--line-soft)' }}>
        <div style={{ font: '500 11px var(--mono)', color: 'var(--fg-3)' }}>
          recall@1
          <b style={{ display: 'block', color: 'var(--ok)', fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em', marginTop: 2 }}>
            {summary.recall_at_1 > 0 ? `${summary.recall_at_1.toFixed(1)}%` : '—'}
          </b>
        </div>
        <div style={{ font: '500 11px var(--mono)', color: 'var(--fg-3)' }}>
          Δ vs. 30d ago
          <b style={{ display: 'block', color: 'var(--ok)', fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em', marginTop: 2 }}>
            —
          </b>
        </div>
        <div style={{ font: '500 11px var(--mono)', color: 'var(--fg-3)' }}>
          resolutions
          <b style={{ display: 'block', color: 'var(--fg)', fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em', marginTop: 2 }}>
            {summary.resolutions.toLocaleString()}
          </b>
        </div>
        <div style={{ font: '500 11px var(--mono)', color: 'var(--fg-3)' }}>
          overrides
          <b style={{ display: 'block', color: 'var(--warn)', fontSize: 18, fontWeight: 600, letterSpacing: '-0.01em', marginTop: 2 }}>
            {summary.overrides.toLocaleString()}
          </b>
        </div>
      </div>
    </div>
  )
}
