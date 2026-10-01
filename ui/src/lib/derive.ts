// Pure aggregation helpers over real store data - every chart/metric in the UI reads
// through these instead of holding a hardcoded number, so a number is always as fresh
// as the last real batch job / decision.
import type { BatchJob, BatchRowFlat, DerivedRow, RowDetail } from './types'

export const DISPOSITION_COLORS: Record<string, string> = {
  restock: '#2563eb',
  refurbish: '#60a5fa',
  liquidate: '#94a3b8',
  dispose: '#ef4444',
  pending_review: '#f59e0b',
}

export type ProductCondition = 'used' | 'damaged' | 'unused' | 'uncertain'
export type DispositionCategory = 'Restock' | 'Refurbish' | 'Liquidate' | 'Dispose' | '—'

export interface ProductReasoning {
  condition: ProductCondition
  disposition: DispositionCategory
  conditionReason: string
  shortConditionReason: string
  dispositionReason: string
  shortDispositionReason: string
  primaryReason: string
  bullets: string[]
  isPerfect: boolean
}

/**
 * Derives the clear condition of the product: 'used', 'damaged', 'unused', or 'uncertain'.
 * Rules:
 * - Keep 'uncertain' if the product is not a match (wrong item)
 * - Keep 'uncertain' if no image of the product is given
 * - Keep 'uncertain' if no clear image is provided / uninspected fail-open
 * - Otherwise: 'damaged', 'unused', or 'used'
 */
export function deriveProductCondition(row: DerivedRow | BatchRowFlat): ProductCondition {
  // 1. Keep uncertain if return photo is missing in the input file
  const hasReturnPhoto = Boolean(
    (row as DerivedRow).image || (row.photo_refs && row.photo_refs.trim().length > 0)
  )
  if (!hasReturnPhoto || row.failure_reason === 'no_return_photo') {
    return 'uncertain'
  }

  // 2. Keep uncertain if the product is not a match (wrong item)
  if (
    row.photo_identity_match === 'no' ||
    Boolean((row as DerivedRow).wrong_item_flag) ||
    row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ||
    row.auto_disapproved === 'true'
  ) {
    return 'uncertain'
  }

  const obs = (row.observed_state || '').toLowerCase()
  const cond = (row.amazon_condition || '').toLowerCase()

  // 3. Damaged
  if (
    obs === 'damaged' ||
    cond === 'damaged' ||
    cond.includes('broken') ||
    cond.includes('shattered')
  ) {
    return 'damaged'
  }

  // 4. Unused (factory sealed or opened unused)
  if (
    obs === 'opened_unused' ||
    obs === 'factory_sealed' ||
    obs === 'intact_sealed' ||
    cond === 'new' ||
    cond === 'used - like new'
  ) {
    return 'unused'
  }

  // 5. Used
  if (obs === 'signs_of_use' || obs === 'used' || cond.startsWith('used')) {
    return 'used'
  }

  // 6. Keep uncertain if no clear image is provided / uninspected
  return 'uncertain'
}

/**
 * The disposition to show: a person's decision if there is one, otherwise the rules engine's route
 * (`agent_disposition`). The UI never works out a route itself; with neither, it shows '—'.
 */
export function deriveProductDisposition(row: DerivedRow | BatchRowFlat): DispositionCategory {
  const explicit = (
    (row as DerivedRow).latest_decision?.new_disposition ||
    row.operator_disposition ||
    ''
  ).toLowerCase()
  if (['restock', 'refurbish', 'liquidate', 'dispose'].includes(explicit)) {
    return (explicit.charAt(0).toUpperCase() + explicit.slice(1)) as DispositionCategory
  }
  const agent = (row.agent_disposition || '').toLowerCase()
  if (['restock', 'refurbish', 'liquidate', 'dispose'].includes(agent)) {
    return (agent.charAt(0).toUpperCase() + agent.slice(1)) as DispositionCategory
  }
  return '—'
}

/**
 * True only when the backend auto-approved the row (batch/auto_approve.py: an engine route, no review,
 * no sign-off, every check passed at the configured confidence, IDs agree). The UI never auto-approves.
 */
export function isPerfectReturn(row: DerivedRow | BatchRowFlat): boolean {
  return row.auto_approved === 'true'
}

/**
 * Derives comprehensive, clear, natural-language business reasoning explaining
 * exactly why the product received its disposition and condition grading.
 */
export function deriveProductReasoning(
  row: DerivedRow | BatchRowFlat,
  detail?: RowDetail | null,
): ProductReasoning {
  const cond = deriveProductCondition(row)
  const disp = deriveProductDisposition(row)
  const perfect = isPerfectReturn(row)

  const obs = (row.observed_state || '').toLowerCase()
  const condRaw = (row.amazon_condition || '').toLowerCase()

  const hasReturnPhoto = Boolean(
    (row as DerivedRow).image || (row.photo_refs && row.photo_refs.trim().length > 0)
  )
  const isReturnPhotoMissing = !hasReturnPhoto || row.failure_reason === 'no_return_photo'

  const isMismatch =
    !isReturnPhotoMissing &&
    (row.photo_identity_match === 'no' ||
      Boolean((row as DerivedRow).wrong_item_flag) ||
      row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ||
      row.auto_disapproved === 'true')

  // 1. Condition Reason & Short Condition Reason
  let conditionReason = ''
  let shortConditionReason = ''

  if (isReturnPhotoMissing) {
    conditionReason =
      'No return photo was supplied, so the condition is uncertain.'
    shortConditionReason = 'Missing return photograph'
  } else if (isMismatch) {
    conditionReason =
      'The returned item does not match the sold record, so its condition is not graded against that product.'
    shortConditionReason = 'Unmatched item cannot be graded'
  } else if (cond === 'damaged') {
    const defectDetails = detail?.judgment?.condition?.observations
      ?.map((d) => `${d.defect_type} (${d.severity})`)
      .join(', ')
    conditionReason = defectDetails
      ? `Physical damage observed in intake evidence: ${defectDetails}.`
      : 'Damage observed in the provided photos.'
    shortConditionReason = 'Damage observed'
  } else if (cond === 'unused') {
    if (obs === 'factory_sealed' || condRaw === 'new') {
      conditionReason =
        'Factory seal observed intact in the provided photos; no wear observed.'
      shortConditionReason = 'Factory sealed & pristine'
    } else {
      conditionReason =
        'No wear observed on the item in the provided photos.'
      shortConditionReason = 'No wear observed'
    }
  } else if (cond === 'used') {
    conditionReason =
      'Signs of use observed in the provided photos.'
    shortConditionReason = 'Signs of customer use'
  } else {
    conditionReason =
      'The provided photos do not establish the condition.'
    shortConditionReason = 'Condition not determinable'
  }

  // 2. Disposition and summary: the backend's own rationale (batch/runner.py build_rationale), which
  // states the evidence and the rules engine's rule. Nothing here adds a claim of its own.
  const latestDecision = (row as DerivedRow).latest_decision
  const rationale = (row.rationale || '').trim()
  const firstSentence = (rationale.split('. ')[0] || '').replace(/[.]$/, '')
  let dispositionReason: string
  let shortDispositionReason: string
  let primaryReason: string
  if (latestDecision?.reason) {
    dispositionReason = `Operator decision (${latestDecision.action.replace('_', ' ')}): ${latestDecision.reason}`
    shortDispositionReason = `Operator ${latestDecision.action.replace('_', ' ')}`
    primaryReason = `Operator decision: ${latestDecision.reason}`
  } else if (rationale) {
    dispositionReason = rationale
    shortDispositionReason =
      disp === '—' ? 'No route computed; needs review' : `Rules engine: ${disp.toLowerCase()}`
    primaryReason = firstSentence
  } else if (isReturnPhotoMissing) {
    dispositionReason = 'No return photo was supplied. No grade and no route were computed; held for review.'
    shortDispositionReason = 'No return photo; needs review'
    primaryReason = 'No return photo supplied. Awaiting review.'
  } else {
    dispositionReason =
      disp === '—'
        ? 'No route was computed for this row; a person decides.'
        : `Rules engine route: ${disp.toLowerCase()}.`
    shortDispositionReason = disp === '—' ? 'Needs review' : `Rules engine: ${disp.toLowerCase()}`
    primaryReason = dispositionReason
  }

  // 3. Key facts, exactly as the backend recorded them
  const identityBullet = isReturnPhotoMissing
    ? 'Identity: not checked (no return photo)'
    : `Identity (photo): ${row.photo_identity_match || 'uncertain'}; records: ${row.sold_vs_returned_id_check || 'not checked'}`
  const missingParts = (row.parts_missing || '').trim()
  const componentBullet = isReturnPhotoMissing
    ? 'Components: not checked (no return photo)'
    : missingParts
    ? `Components: missing in clear view: ${missingParts}`
    : 'Components: none confirmed missing (parts out of frame are named in the rationale)'

  const bullets: string[] = [
    identityBullet,
    `Condition: ${row.amazon_condition || 'uncertain'} — ${shortConditionReason}`,
    componentBullet,
    `Disposition: ${disp === '—' ? 'none computed' : disp.toUpperCase()} — ${shortDispositionReason}`,
  ]

  return {
    condition: cond,
    disposition: disp,
    conditionReason,
    shortConditionReason,
    dispositionReason,
    shortDispositionReason,
    primaryReason,
    bullets,
    isPerfect: perfect,
  }
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
    const disp = deriveProductDisposition(row)
    if (disp !== '—') {
      const key = disp.toLowerCase()
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
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
  return rows.filter(
    (r) =>
      !r.wrong_item_flag &&
      (r.latest_decision?.action === 'review_request' ||
        r.status === 'Awaiting review' ||
        r.status === 'Needs attention'),
  )
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
