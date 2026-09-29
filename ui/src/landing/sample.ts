// Sample data for the landing page. Nothing here is a real return: the page labels every mockup
// "Sample data" (FACTS.md 0.2). Each outcome is what the real rules engine computes for these
// inputs with the current params. ui/sample-data/verify_samples.py asserts it (case keys below).
//
// The through-line unit is SKU-LAMP-LED, a reference card in reference/products/ (itself a synthetic
// placeholder card): "LED desk lamp with USB cable", electronics; lamp (essential), usb cable
// (essential, replaceable), manual (non-essential); critical features on the body: a round weighted
// matte-black base (~12 cm) and a touch switch on the arm.

export const unit = {
  returnId: 'RTN-SAMPLE-0142',
  unitId: 'UNIT-SAMPLE-0142',
  orderId: 'ORD-SAMPLE-8810',
  sku: 'SKU-LAMP-LED',
  asin: 'B0DUMMY357',
  product: 'LED desk lamp with USB cable',
  category: 'Electronics',
  listPrice: '₹2,499',
  photos: 3,
}

// Product identity (photo): fusion.py, barcode matches_ordered + model yes → yes (strong).
export const identity = {
  verdict: 'Yes' as const,
  strength: 'strong',
  features: [
    { name: 'Round weighted matte-black base', where: 'product body', result: 'match' as const },
    { name: 'Touch switch on the arm', where: 'product body', result: 'match' as const },
  ],
  barcode: 'Barcode matches ordered SKU',
}

// Sold vs returned records: batch/runner.py check_id_match → "matched".
export const records = [
  { field: 'Order ID', sold: 'ORD-SAMPLE-8810', returned: 'ORD-SAMPLE-8810' },
  { field: 'SKU', sold: 'SKU-LAMP-LED', returned: 'SKU-LAMP-LED' },
  { field: 'ASIN', sold: 'B0DUMMY357', returned: 'B0DUMMY357' },
]

export type PartState = 'present' | 'missing' | 'uncertain'
export const parts: { name: string; essential: boolean; replaceable: boolean; state: PartState; note: string }[] = [
  { name: 'Lamp', essential: true, replaceable: false, state: 'present', note: 'Observed present' },
  { name: 'USB cable', essential: true, replaceable: true, state: 'missing', note: 'Absent in clear view' },
  { name: 'Manual', essential: false, replaceable: true, state: 'present', note: 'Observed present' },
]

// Condition: observed_state opened_unused; grade used_like_new (electronics rubric text, short quote).
export const condition = {
  observedState: 'Opened, unused',
  defects: 'No damage observed in the provided photos',
  grade: 'Used - Like New',
  rubricQuote: 'absolutely no signs of wear',
  functional: 'Functional test not performed',
  snapshot: 'amazon-uk-condition-guidelines-2020-12-electronics',
}

// Engine outcome for the lamp: verify_samples.py case "missing_cable" → refurbish, R09, no review, no sign-off.
export const recommendation = {
  route: 'Refurbish' as const,
  rule: 'R09',
  why: 'Replaceable essential part missing; net gain covers the refurbish cost',
  reviewReasons: [] as string[],
  signoff: 'Not required (below the ₹5,000 high-value threshold)',
  autoApprove: 'Not auto-approved: the completeness check did not pass',
}

export const dispositions = ['Restock', 'Refurbish', 'Liquidate', 'Dispose'] as const

// Other engine-verified outcomes shown as a compact table (verify_samples.py case keys).
export const otherOutcomes = [
  { key: 'clean', scenario: 'Home & kitchen item, complete, Used - Like New', route: 'Restock', rule: 'R13', flag: '' },
  { key: 'used_good', scenario: 'Home & kitchen item, complete, Used - Good', route: 'Liquidate', rule: 'R14', flag: '' },
  { key: 'lid_not_visible', scenario: 'Essential lid not visible in the provided photos', route: 'Liquidate', rule: 'R10', flag: 'Review · provisional' },
  { key: 'damaged_low_value', scenario: 'Severe damage, low list price', route: 'Dispose', rule: 'R10', flag: 'Sign-off (S01)' },
  { key: 'high_value_electronics', scenario: 'Opened electronics, list price ₹9,999', route: 'Refurbish', rule: 'R11', flag: 'Sign-off (S02)' },
  { key: 'identity_uncertain', scenario: 'Product identity uncertain', route: 'No recommendation', rule: 'R03b', flag: 'Review' },
]

// Exceptions: real review / no-recommendation codes (FACTS.md §5) with human-readable labels.
export const exceptions: { code: string; label: string; effect: string; tone: 'danger' | 'warning' }[] = [
  { code: 'wrong_item_returned', label: 'Identity mismatch: possible product swap', effect: 'No recommendation. Requires review.', tone: 'danger' },
  { code: 'identity_unverified', label: 'Product identity uncertain', effect: 'No recommendation. Requires review.', tone: 'warning' },
  { code: 'essential_component_uncertain', label: 'Essential part not visible in the provided photos', effect: 'Routed as if missing, provisional. Requires review.', tone: 'warning' },
  { code: 'condition_uncertain', label: 'Condition uncertain', effect: 'No recommendation. Requires review.', tone: 'warning' },
  { code: 'possible_reused_photo', label: 'Possible reused photo', effect: 'Route kept, flagged for review.', tone: 'warning' },
  { code: 'injection_attempt_suspected', label: 'Instruction-like text found in a photo', effect: 'Route kept, flagged for review.', tone: 'warning' },
  { code: 'inspection_incomplete', label: 'Inspection incomplete', effect: 'No recommendation. Requires review.', tone: 'warning' },
  { code: 'no_product_reference', label: 'No product reference on file', effect: 'Model not called. Requires review.', tone: 'warning' },
]

// Audit trail: real chain event types (chain/event_types.py) and actor types (migration 0008).
export const events: { t: string; type: string; actor: string; label: string; result: string }[] = [
  { t: '10:02:11', type: 'return_created', actor: 'operator', label: 'Return created', result: 'RTN-SAMPLE-0142' },
  { t: '10:02:40', type: 'photo_received', actor: 'operator', label: 'Photos received', result: '3 photos stored before any model call' },
  { t: '10:02:41', type: 'photo_quality_assessed', actor: 'system', label: 'Photo quality assessed', result: '3 usable' },
  { t: '10:02:43', type: 'inspection_started', actor: 'system', label: 'Inspection started', result: 'One judgment session' },
  { t: '10:02:58', type: 'inspection_completed', actor: 'system', label: 'Inspection completed', result: 'Observations validated by code' },
  { t: '10:02:58', type: 'identity_fused', actor: 'system', label: 'Identity fused', result: 'Product identity: Yes' },
  { t: '10:02:58', type: 'disposition_computed', actor: 'system', label: 'Disposition computed', result: 'Refurbish · R09' },
  { t: '10:07:15', type: 'operator_decision_recorded', actor: 'operator', label: 'Operator decision', result: 'Accepted' },
  { t: '10:07:15', type: 'record_finalized', actor: 'system', label: 'Record finalised', result: 'Evidence record hashed' },
]

// Dashboard preview: the tiles and charts the real Dashboard computes (FACTS.md §7); values are sample.
export const dashboard = {
  tiles: [
    { label: 'Total returns', value: '128' },
    { label: 'Auto-approved', value: '41' },
    { label: 'Needs attention', value: '17' },
    { label: 'Restock eligible', value: '52' },
  ],
  mix: [
    { label: 'Restock', value: 52 },
    { label: 'Refurbish', value: 29 },
    { label: 'Liquidate', value: 21 },
    { label: 'Dispose', value: 9 },
    { label: 'Pending review', value: 17 },
  ],
  perUpload: [22, 31, 18, 27, 30],
}
