export function fmtConfidence(c: number | null | undefined): string {
  if (c == null) return '—'
  return `${Math.round(c * 100)}%`
}

export function fmtLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function fmtTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function fmtCurrency(usd: number): string {
  if (usd < 0.005) return '<$0.01'
  return `$${usd.toFixed(2)}`
}

export function fmtPercent(v: number, total: number): string {
  if (total === 0) return '0%'
  return `${Math.round((v / total) * 100)}%`
}
