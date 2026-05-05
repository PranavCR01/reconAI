export type HypState = 'done' | 'fail' | 'active' | 'pending'

export interface HypothesisItem {
  name: string
  state: HypState
}

const HYP_STYLE: Record<HypState, { color: string; bg: string; border: string }> = {
  done:    { color: 'var(--ok)',   bg: 'oklch(0.24 0.04 155 / 0.4)', border: 'oklch(0.40 0.10 155)' },
  fail:    { color: 'var(--p1)',   bg: 'oklch(0.26 0.06 25 / 0.4)',  border: 'oklch(0.45 0.12 25)'  },
  active:  { color: 'var(--warn)', bg: 'oklch(0.28 0.06 75 / 0.5)',  border: 'oklch(0.50 0.10 75)'  },
  pending: { color: 'var(--fg-3)', bg: 'var(--bg-2)',                 border: 'var(--line-soft)'     },
}

const CHECK: Record<HypState, string> = {
  done: '✓',
  fail: '✕',
  active: '◐',
  pending: '·',
}

interface HypothesisPillsProps {
  hypotheses: HypothesisItem[]
}

export function HypothesisPills({ hypotheses }: HypothesisPillsProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <span style={{ font: '500 10.5px var(--mono)', fontFamily: 'var(--mono)', fontSize: 10.5, fontWeight: 500, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginRight: 4 }}>
        Hypotheses
      </span>
      {hypotheses.map((h) => {
        const s = HYP_STYLE[h.state]
        return (
          <span
            key={h.name}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              height: 22,
              padding: '0 8px',
              borderRadius: 11,
              fontFamily: 'var(--mono)',
              fontSize: 11,
              fontWeight: 500,
              color: s.color,
              background: s.bg,
              border: `1px solid ${s.border}`,
              animation: h.state === 'active' ? 'spin 1s linear infinite' : undefined,
            }}
          >
            <span style={{ width: 10, height: 10, display: 'grid', placeItems: 'center', fontSize: 10, animation: h.state === 'active' ? 'spin 1s linear infinite' : undefined }}>
              {CHECK[h.state]}
            </span>
            {h.name}
          </span>
        )
      })}
    </div>
  )
}
