import type { DeploymentCorrelation } from '@/types'

interface Props {
  data: DeploymentCorrelation[]
}

function SigmaCell({ sigma }: { sigma: number }) {
  const color = sigma >= 3.0 ? 'var(--p1)' : sigma >= 1.5 ? 'var(--warn)' : 'var(--fg-2)'
  const cls = sigma >= 3.0 ? 'up' : sigma < 0 ? 'down' : 'flat'
  const sign = sigma > 0 ? '+' : ''
  return (
    <span style={{ font: '600 13px var(--mono)', color }}>
      {sigma >= 0 ? `+${Math.round(Math.abs(sigma * 10))}` : `-${Math.round(Math.abs(sigma * 10))}`}
      <span style={{ display: 'inline-block', fontSize: 10.5, color: 'var(--fg-3)', fontWeight: 500, marginLeft: 4 }}>
        σ={sigma.toFixed(1)}
      </span>
    </span>
  )
}

function StatusPill({ status }: { status: DeploymentCorrelation['status'] }) {
  const config = {
    investigating: {
      bg: 'oklch(0.32 0.07 75 / 0.5)',
      color: 'oklch(0.93 0.10 75)',
      border: 'oklch(0.50 0.13 75)',
      dot: 'var(--warn)',
      animate: true,
      label: 'investigating',
    },
    resolved: {
      bg: 'oklch(0.30 0.07 155 / 0.5)',
      color: 'oklch(0.92 0.10 155)',
      border: 'oklch(0.40 0.10 155)',
      dot: 'var(--ok)',
      animate: false,
      label: 'resolved',
    },
    normal: {
      bg: 'oklch(0.30 0.07 155 / 0.5)',
      color: 'oklch(0.92 0.10 155)',
      border: 'oklch(0.40 0.10 155)',
      dot: 'var(--ok)',
      animate: false,
      label: 'normal',
    },
  }
  const c = config[status] ?? config.normal
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      height: 22, padding: '0 8px', borderRadius: 4,
      font: '500 11px var(--mono)',
      background: c.bg, color: c.color, border: `1px solid ${c.border}`,
    }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%', background: c.dot,
        animation: c.animate ? 'bk 1.4s ease-in-out infinite' : undefined,
      }} />
      {c.label}
    </span>
  )
}

function fmtDate(iso: string) {
  const d = new Date(iso)
  return d.toISOString().slice(0, 16).replace('T', ' ') + 'Z'
}

export function DeploymentTable({ data }: Props) {
  const spikeCount = data.filter(d => d.sigma >= 3.0).length

  return (
    <>
      <style>{`@keyframes bk { 0%,100%{opacity:.5} 50%{opacity:1} }`}</style>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {['Deployment', 'Date', 'Incidents +24h', 'Most affected', 'Suspected root cause', 'Status'].map((h, i) => (
                <th key={h} style={{
                  font: '600 10.5px var(--mono)', textTransform: 'uppercase', letterSpacing: '0.08em',
                  color: 'var(--fg-3)', textAlign: i === 2 ? 'right' : 'left',
                  padding: '8px 12px', background: 'var(--bg)', borderBottom: '1px solid var(--line)',
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((dep) => (
              <tr key={dep.deploy_name + dep.deployed_at}
                style={{ cursor: 'default' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).querySelectorAll('td').forEach(td => (td.style.background = 'var(--bg-2)')) }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).querySelectorAll('td').forEach(td => (td.style.background = '')) }}
              >
                <td style={{ padding: '11px 12px', borderBottom: '1px dashed var(--line-soft)' }}>
                  <span style={{ font: '500 12px var(--mono)', color: 'var(--fg)' }}>
                    {dep.deploy_name}
                    {dep.description && (
                      <small style={{ display: 'block', color: 'var(--fg-3)', fontSize: 10.5, marginTop: 2, fontWeight: 500 }}>
                        {dep.description}
                      </small>
                    )}
                  </span>
                </td>
                <td style={{ padding: '11px 12px', borderBottom: '1px dashed var(--line-soft)' }}>
                  <span style={{ font: '500 11.5px var(--mono)', color: 'var(--fg-1)' }}>
                    {fmtDate(dep.deployed_at)}
                  </span>
                </td>
                <td style={{ padding: '11px 12px', borderBottom: '1px dashed var(--line-soft)', textAlign: 'right' }}>
                  <SigmaCell sigma={dep.sigma} />
                </td>
                <td style={{ padding: '11px 12px', borderBottom: '1px dashed var(--line-soft)' }}>
                  <span style={{ font: '500 12px var(--mono)', color: 'var(--fg-1)' }}>
                    {dep.most_affected_object ?? '—'}
                  </span>
                </td>
                <td style={{ padding: '11px 12px', borderBottom: '1px dashed var(--line-soft)' }}>
                  <span style={{ font: '500 11.5px var(--mono)', color: dep.suspected_root_cause ? 'var(--fg-2)' : 'var(--fg-3)' }}>
                    {dep.suspected_root_cause ?? 'no significant correlation'}
                  </span>
                </td>
                <td style={{ padding: '11px 12px', borderBottom: '1px dashed var(--line-soft)' }}>
                  <StatusPill status={dep.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ padding: '14px 16px 16px', borderTop: '1px solid var(--line)', font: '500 11px var(--mono)', color: 'var(--fg-3)', lineHeight: 1.6 }}>
        Significance threshold <code style={{ background: 'var(--bg-2)', padding: '1px 5px', borderRadius: 3, color: 'var(--fg-1)' }}>σ ≥ 3.0</code> against 14-day baseline · jump-detection algorithm · {spikeCount} deployment{spikeCount !== 1 ? 's' : ''} with significant correlation in window.
      </div>
    </>
  )
}
