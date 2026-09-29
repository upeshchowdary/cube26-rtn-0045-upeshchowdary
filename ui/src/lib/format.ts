export function moneyMinor(minor: number, currency: string): string {
  const symbol = currency === 'INR' ? '₹' : currency === 'USD' ? '$' : `${currency} `
  return `${symbol}${(minor / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

export function bpToPercent(bp: number): string {
  return `${Math.round(bp / 100)}%`
}

export function titleCase(value: string): string {
  return value
    .split('_')
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(' ')
}

export function timeAgo(unixSeconds: number): string {
  const diffMs = Date.now() - unixSeconds * 1000
  const mins = Math.max(0, Math.round(diffMs / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs} hr`
  return `${Math.round(hrs / 24)} day`
}

export function formatDateTime(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
