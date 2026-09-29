// Pure aggregation helpers over real store data - every chart/metric in the UI reads
// through these instead of holding a hardcoded number, so a number is always as fresh
// as the last real batch job / decision.
import type { BatchJob, DerivedRow } from './types'

export const DISPOSITION_COLORS: Record<string, string> = {
  restock: '#2fa866',
  refurbish: '#347d70',
  liquidate: '#477e9b',
  dispose: '#caa255',
  pending_review: '#8da296',
}

export function dispositionLabel(value: string): string {
  if (!value) return 'Pending review'
  return value
    .split('_')
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ')
}

/** Label for the backend's `sold_vs_returned_id_check` string. PASS only for an exact
 * "matched" (every ID present on both records and equal); a blank ID is "not checked". */
export function idCheckLabel(check: string | undefined): 'PASS' | 'FAIL' | 'NOT CHECKED' {
  if (check === 'matched') return 'PASS'
  if (check?.startsWith('NOT MATCHED')) return 'FAIL'
  return 'NOT CHECKED'
}

export function dispositionMix(rows: DerivedRow[]): { name: string; value: number; key: string }[] {
  const counts = new Map<string, number>()
  for (const row of rows) {
    const key = row.operator_disposition || 'pending_review'
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({ key, name: dispositionLabel(key), value }))
}

export function identityDistribution(rows: DerivedRow[]): { name: string; value: number }[] {
  let mismatch = 0
  let uncertain = 0
  let ok = 0
  for (const row of rows) {
    if (row.wrong_item_flag) {
      mismatch++
    } else if (row.observed_state === 'uncertain') {
      uncertain++
    } else {
      ok++
    }
  }
  return [
    { name: 'Matched', value: ok },
    { name: 'Uncertain', value: uncertain },
    { name: 'Mismatch', value: mismatch },
  ]
}

export function conditionDistribution(rows: DerivedRow[]): { name: string; value: number }[] {
  const counts = new Map<string, number>()
  for (const row of rows) {
    const grade = row.amazon_condition || 'uncertain'
    counts.set(grade, (counts.get(grade) ?? 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([name, value]) => ({ name, value }))
}

export function topMissingComponents(rows: DerivedRow[], limit = 6): { name: string; value: number }[] {
  const counts = new Map<string, number>()
  for (const row of rows) {
    for (const part of row.parts_missing.split(';').map((p) => p.trim()).filter(Boolean)) {
      counts.set(part, (counts.get(part) ?? 0) + 1)
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([name, value]) => ({ name, value }))
}

export function rowsPerJob(jobs: BatchJob[]): { label: string; total: number; processed: number; uncertain: number }[] {
  return [...jobs]
    .filter((j) => j.status === 'done')
    .sort((a, b) => a.created_at - b.created_at)
    .map((j) => ({
      label: new Date(j.created_at * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      total: j.total_rows,
      processed: j.processed,
      uncertain: j.uncertain,
    }))
}

export function needsAttention(rows: DerivedRow[]): DerivedRow[] {
  return rows.filter((r) => r.status === 'Awaiting review' || r.status === 'Needs attention')
}

export function reviewQueue(rows: DerivedRow[]): DerivedRow[] {
  return rows.filter((r) => r.latest_decision?.action === 'review_request' || (!r.latest_decision && r.status !== 'Finalized'))
}

export function distinctSkus(rows: DerivedRow[]): { sku: string; asin: string; image: string | null; count: number }[] {
  const bySku = new Map<string, { sku: string; asin: string; image: string | null; count: number }>()
  for (const row of rows) {
    const existing = bySku.get(row.ordered_sku)
    if (existing) {
      existing.count++
      if (!existing.image && row.image) existing.image = row.image
    } else {
      bySku.set(row.ordered_sku, { sku: row.ordered_sku, asin: row.ordered_asin, image: row.image, count: 1 })
    }
  }
  return [...bySku.values()].sort((a, b) => b.count - a.count)
}
