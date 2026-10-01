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
  // 1. Keep uncertain if the product is not a match (wrong item)
  if (
    row.photo_identity_match === 'no' ||
    Boolean((row as DerivedRow).wrong_item_flag) ||
    row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ||
    row.auto_disapproved === 'true'
  ) {
    return 'uncertain'
  }

  // 2. Keep uncertain if no image of the product is given
  const hasPhoto = Boolean(
    (row as DerivedRow).image || (row.photo_refs && row.photo_refs.trim().length > 0)
  )
  if (!hasPhoto || row.failure_reason === 'no_return_photo') {
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
 * Derives the category of disposition:
 * - Restock — item can go back on shelf
 * - Refurbish — item needs repair or repackaging
 * - Liquidate — sell at reduced value
 * - Dispose — item has no recoverable value
 */
export function deriveProductDisposition(row: DerivedRow | BatchRowFlat): DispositionCategory {
  // 1. Operator manual override / finalized decision
  const explicit = (
    (row as DerivedRow).latest_decision?.new_disposition ||
    row.operator_disposition ||
    ''
  ).toLowerCase()
  if (['restock', 'refurbish', 'liquidate', 'dispose'].includes(explicit)) {
    return (explicit.charAt(0).toUpperCase() + explicit.slice(1)) as DispositionCategory
  }

  // 2. Model / agent recommended disposition
  const agent = (row.agent_disposition || '').toLowerCase()
  if (['restock', 'refurbish', 'liquidate', 'dispose'].includes(agent)) {
    return (agent.charAt(0).toUpperCase() + agent.slice(1)) as DispositionCategory
  }

  // 3. Wrong item returned has no recoverable catalog value -> Dispose
  if (
    row.photo_identity_match === 'no' ||
    Boolean((row as DerivedRow).wrong_item_flag) ||
    row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ||
    row.auto_disapproved === 'true'
  ) {
    return 'Dispose'
  }

  // 4. Physical condition fallbacks
  const obs = (row.observed_state || '').toLowerCase()
  const cond = (row.amazon_condition || '').toLowerCase()

  // Damaged has no recoverable value -> Dispose
  if (obs === 'damaged' || cond === 'damaged' || cond.includes('broken') || cond.includes('shattered')) {
    return 'Dispose'
  }

  // Consumable opened / used -> Dispose
  const isConsumable =
    row.ordered_sku?.toLowerCase().includes('cereal') ||
    row.ordered_sku?.toLowerCase().includes('shampoo')
  if (isConsumable && (obs === 'signs_of_use' || cond.startsWith('used'))) {
    return 'Dispose'
  }

  // Intact / sealed / new -> Restock
  if (obs === 'factory_sealed' || cond === 'new') {
    return 'Restock'
  }

  // Opened unused
  if (obs === 'opened_unused' || cond === 'used - like new') {
    const missing = (row.parts_missing || '').trim()
    const hasMissing = missing && missing !== '—' && missing !== '-' && missing.toLowerCase() !== 'none'
    return hasMissing ? 'Refurbish' : 'Restock'
  }

  // Used items
  if (obs === 'signs_of_use' || obs === 'used' || cond.startsWith('used')) {
    const missing = (row.parts_missing || '').trim()
    const hasMissing = missing && missing !== '—' && missing !== '-' && missing.toLowerCase() !== 'none'
    return hasMissing ? 'Refurbish' : 'Liquidate'
  }

  // No image or completely uninspected
  const hasPhoto = Boolean(
    (row as DerivedRow).image || (row.photo_refs && row.photo_refs.trim().length > 0)
  )
  if (!hasPhoto || row.failure_reason === 'no_return_photo') {
    return '—'
  }

  return '—'
}

/**
 * Checks if a return is completely perfect:
 * - Genuine catalog match (no wrong item, no paperwork ID mismatch)
 * - Has valid intake photo
 * - Condition is unused / pristine / factory sealed
 * - No missing parts / all components present
 * - Disposition is Restock
 *
 * Perfect returns are auto-approved and route directly to the Finalized section.
 */
export function isPerfectReturn(row: DerivedRow | BatchRowFlat): boolean {
  if (
    row.photo_identity_match === 'no' ||
    Boolean((row as DerivedRow).wrong_item_flag) ||
    row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ||
    row.auto_disapproved === 'true'
  ) {
    return false
  }

  const hasPhoto = Boolean(
    (row as DerivedRow).image || (row.photo_refs && row.photo_refs.trim().length > 0)
  )
  if (!hasPhoto || row.failure_reason === 'no_return_photo') {
    return false
  }

  const cond = deriveProductCondition(row)
  if (cond !== 'unused') {
    return false
  }

  const missing = (row.parts_missing || '').trim()
  if (missing && missing !== '—' && missing !== '-' && missing.toLowerCase() !== 'none') {
    return false
  }

  const disp = deriveProductDisposition(row)
  if (disp !== 'Restock') {
    return false
  }

  return true
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
  const sku = (row.ordered_sku || '').toLowerCase()
  const isConsumable =
    sku.includes('cereal') || sku.includes('shampoo') || sku.includes('snack') || sku.includes('food')
  const isMismatch =
    row.photo_identity_match === 'no' ||
    Boolean((row as DerivedRow).wrong_item_flag) ||
    row.sold_vs_returned_id_check?.startsWith('NOT MATCHED') ||
    row.auto_disapproved === 'true'
  const hasPhoto = Boolean(
    (row as DerivedRow).image || (row.photo_refs && row.photo_refs.trim().length > 0)
  )

  // 1. Condition Reason & Short Condition Reason
  let conditionReason = ''
  let shortConditionReason = ''

  if (isMismatch) {
    conditionReason =
      'Condition cannot be reliably graded against catalog specs because the returned item does not match the sold record.'
    shortConditionReason = 'Unmatched item cannot be graded'
  } else if (!hasPhoto || row.failure_reason === 'no_return_photo') {
    conditionReason =
      'Condition is uncertain because no returned product photograph was provided for visual inspection.'
    shortConditionReason = 'No return photo provided'
  } else if (cond === 'damaged') {
    const defectDetails = detail?.judgment?.condition?.observations
      ?.map((d) => `${d.defect_type} (${d.severity})`)
      .join(', ')
    conditionReason = defectDetails
      ? `Physical damage observed in intake evidence: ${defectDetails}.`
      : 'Physical or cosmetic damage detected on the returned unit/packaging exceeding standard return tolerance.'
    shortConditionReason = 'Physical damage detected'
  } else if (cond === 'unused') {
    if (obs === 'factory_sealed' || condRaw === 'new') {
      conditionReason =
        'Original manufacturer factory seal is intact and packaging is completely unopened. Zero signs of wear or handling.'
      shortConditionReason = 'Factory sealed & pristine'
    } else {
      conditionReason =
        'Packaging has been opened, but the item itself is in pristine, unhandled condition with zero cosmetic wear or blemishes.'
      shortConditionReason = 'Opened packaging, contents unused'
    }
  } else if (cond === 'used') {
    conditionReason =
      'Item exhibits clear indicators of prior customer usage, unsealed packaging, or cosmetic surface handling marks.'
    shortConditionReason = 'Signs of customer use'
  } else {
    conditionReason =
      'Intake imagery was insufficient or inconclusive for definitive physical condition grading.'
    shortConditionReason = 'Inconclusive intake imagery'
  }

  // 2. Disposition Reason & Short Disposition Reason
  let dispositionReason = ''
  let shortDispositionReason = ''

  const latestDecision = (row as DerivedRow).latest_decision
  if (latestDecision?.reason) {
    dispositionReason = `Operator finalized decision: ${latestDecision.reason} (${latestDecision.action.replace('_', ' ')})`
    shortDispositionReason = `Operator finalized (${latestDecision.action.replace('_', ' ')})`
  } else if (isMismatch) {
    const mismatchDetail =
      row.sold_vs_returned_id_check?.replace(/^NOT MATCHED:\s*/, '') || 'Item or paperwork mismatch'
    dispositionReason = `Returned item identity mismatch: ${mismatchDetail}. Non-matching merchandise cannot be restored to inventory or resold as the sold catalog item.`
    shortDispositionReason = 'Wrong item returned — dispose'
  } else if (perfect) {
    dispositionReason =
      '100% catalog match and complete with all standard components in pristine, unused condition. Auto-approved for immediate shelf restock.'
    shortDispositionReason = '100% complete & sealed — restock'
  } else if (disp === 'Restock') {
    dispositionReason =
      'Item is verified authentic, unused, and complete with all accessories. Eligible for immediate inventory restocking.'
    shortDispositionReason = 'Unused & complete — return to shelf'
  } else if (disp === 'Refurbish') {
    const partsMissing = (row.parts_missing || '').trim()
    if (partsMissing && partsMissing !== '—' && partsMissing !== '-') {
      dispositionReason = `Product is functional and in good condition, but missing standard components (${partsMissing}). Routed to refurbishment for accessory replenishment and repackaging.`
      shortDispositionReason = `Missing ${partsMissing} — refurbish`
    } else {
      dispositionReason =
        'Unit is physically intact but packaging is opened or requires repackaging and cleaning before certified resale.'
      shortDispositionReason = 'Repackaging & testing required'
    }
  } else if (disp === 'Liquidate') {
    dispositionReason =
      'Unit shows signs of prior customer usage but remains complete and functionally intact. Cannot be sold as new; routed to secondary liquidation channels to maximize net recovery.'
    shortDispositionReason = 'Used complete unit — liquidate'
  } else if (disp === 'Dispose') {
    if (isConsumable) {
      dispositionReason = `Opened health, beauty, or food consumable (${row.ordered_sku}). Health and safety compliance policies strictly prohibit restocking opened consumables; routed for disposal.`
      shortDispositionReason = 'Opened consumable — health & safety disposal'
    } else if (cond === 'damaged') {
      dispositionReason =
        'Physical casing or display damage exceeds secondary market recovery value. Repair costs outweigh projected resale value; routed for scrap/salvage disposal.'
      shortDispositionReason = 'Severe damage — scrap/salvage'
    } else {
      dispositionReason =
        'Item has no recoverable market value or fails compliance standards. Routed for safe destruction/disposal.'
      shortDispositionReason = 'No recoverable value — dispose'
    }
  } else {
    dispositionReason = 'Row requires operator evaluation and manual disposition assignment.'
    shortDispositionReason = 'Requires operator review'
  }

  // 3. Primary Reason (authoritative summary sentence)
  let primaryReason = ''
  if (latestDecision?.reason) {
    primaryReason = `Operator decision: ${latestDecision.reason}`
  } else if (isMismatch) {
    primaryReason = `Wrong item returned (${row.sold_vs_returned_id_check?.replace(/^NOT MATCHED:\s*/, '') || 'identity mismatch'}). Auto-disapproved.`
  } else if (perfect) {
    primaryReason =
      'Pristine factory condition, complete components, and 100% verified catalog match. Auto-approved for immediate restock.'
  } else if (disp === 'Restock') {
    primaryReason = 'Item is unused and complete with all components. Ready for immediate inventory restock.'
  } else if (disp === 'Refurbish') {
    primaryReason = row.parts_missing
      ? `Functional unit in good condition, missing standard accessories (${row.parts_missing}). Routed to refurbishment.`
      : 'Unit requires repackaging, inspection, and cleaning before resale.'
  } else if (disp === 'Liquidate') {
    primaryReason =
      'Complete working unit showing signs of customer handling. Routed to liquidation channels.'
  } else if (disp === 'Dispose') {
    if (isConsumable) {
      primaryReason =
        'Opened consumable product with broken seal. Health compliance prohibits restocking; routed for disposal.'
    } else if (cond === 'damaged') {
      primaryReason =
        'Damaged unit with repair cost exceeding salvage recovery value. Routed for disposal.'
    } else {
      primaryReason = 'No recoverable inventory value. Routed for disposal.'
    }
  } else if (!hasPhoto) {
    primaryReason = 'No return photograph provided in intake record. Awaiting manual review.'
  } else {
    primaryReason = 'Intake inspection requires manual verification.'
  }

  // 4. Bullets (Key factual evidence points)
  const missingParts = (row.parts_missing || '').trim()
  const bullets: string[] = [
    isMismatch
      ? `Identity: Mismatch (${row.sold_vs_returned_id_check || 'Returned item does not match sold SKU'})`
      : `Identity: 100% Verified (${row.ordered_sku}, ASIN: ${row.ordered_asin || 'n/a'})`,
    `Condition: ${cond.toUpperCase()} — ${shortConditionReason}`,
    missingParts && missingParts !== '—' && missingParts !== '-' && missingParts.toLowerCase() !== 'none'
      ? `Components: Incomplete (Missing: ${missingParts})`
      : 'Components: 100% Complete (All standard parts present)',
    `Disposition: ${disp.toUpperCase()} — ${shortDispositionReason}`,
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
