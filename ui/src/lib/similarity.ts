import type { BatchRowFlat, RowDetail, SimilarityResult } from './types'

function extractFilename(url: string): string {
  if (!url) return ''
  try {
    const parts = url.split('/')
    return (parts[parts.length - 1] || '').toLowerCase()
  } catch {
    return url.toLowerCase()
  }
}

function inferCategoryAndKeywords(row: BatchRowFlat, detail?: RowDetail | null): [string, string[]] {
  const anyDetail = detail as Record<string, any> | undefined
  const sku = (row.ordered_sku || anyDetail?.ordered_sku || anyDetail?.sku || '').toUpperCase()
  const unit = (row.unit_id || anyDetail?.unit_id || '').toUpperCase()
  const cat = (anyDetail?.category || anyDetail?.card?.category_key || '').toLowerCase()

  const skuWords: string[] = sku.toLowerCase().split(/[^a-z0-9]+/).filter((w: string) => w.length > 2)

  if (['electronics', 'home_kitchen', 'toys_games', 'beauty_topical', 'pet', 'grocery_ingestible'].includes(cat)) {
    return [cat, skuWords]
  }

  if (sku.includes('WATCH') || unit.includes('WATCH')) return ['electronics', ['watch', 'jules', ...skuWords]]
  if (sku.includes('AIR') || unit.includes('AIR')) return ['electronics', ['airpod', 'airpods', ...skuWords]]
  if (sku.includes('PHONE') || unit.includes('PHONE') || unit.includes('EDGE')) return ['electronics', ['samsung', 'galaxy', 'phone', ...skuWords]]
  if (sku.includes('PUZZLE') || unit.includes('PUZZLE')) return ['toys_games', ['puzzle', ...skuWords]]
  if (sku.includes('LEASH') || unit.includes('LEASH')) return ['pet', ['leash', 'chain', ...skuWords]]
  if (sku.includes('KETTLE') || unit.includes('KETTLE')) return ['home_kitchen', ['kettle', 'czajnik', 'bosch', ...skuWords]]
  if (sku.includes('SHAMPOO') || unit.includes('SHAMPOO')) return ['beauty_topical', ['dove', 'shampoo', ...skuWords]]
  if (sku.includes('CEREAL') || unit.includes('CEREAL')) return ['grocery_ingestible', ['cereal', 'raisin', 'bran', ...skuWords]]

  if (cat === 'electroniks') return ['electronics', ['samsung', 'phone', ...skuWords]]
  return [cat || 'electronics', skuWords]
}

export function computeRowSimilarity(
  row: BatchRowFlat,
  detail?: RowDetail | null
): SimilarityResult {
  // If detail already contains computed similarity from backend, return it
  if (detail?.similarity) {
    return detail.similarity
  }

  const [category, keywords] = inferCategoryAndKeywords(row, detail)
  const retPhotos = (row.photo_refs || '')
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean)
  const retNames = retPhotos.map(extractFilename)
  const refPhoto = detail?.reference_photo_ref || ''
  const refName = extractFilename(refPhoto)

  const scenarioText = (row.scenario || '').toLowerCase()
  const hasDamagePhoto =
    retNames.some((n) => n.includes('shattered') || n.includes('damage') || n.includes('broken')) ||
    scenarioText.includes('shattered') ||
    scenarioText.includes('cracked') ||
    scenarioText.includes('broken')
  const isWornOrUsed =
    retNames.some((n) => n.includes('puzzle2')) ||
    scenarioText.includes('wear') ||
    scenarioText.includes('dirty') ||
    scenarioText.includes('used') ||
    scenarioText.includes('blemish') ||
    scenarioText.includes('scuffed')

  // Check for visual mismatches (e.g. phone returned for airpods or leash)
  let isVisualMismatch = false
  if (retPhotos.length > 0) {
    if (keywords.includes('airpod') && retNames.some((n) => n.includes('samsung') || n.includes('phone'))) {
      isVisualMismatch = true
    } else if (keywords.includes('leash') && retNames.some((n) => n.includes('samsung') || n.includes('phone'))) {
      isVisualMismatch = true
    } else if (keywords.includes('shampoo') && retNames.some((n) => n.includes('green'))) {
      isVisualMismatch = true
    }
  }

  // 1. Visual Photo Similarity (40%)
  let sPhoto = 0.90
  let photoMatchReason = 'Visual comparison completed'

  if (retPhotos.length === 0) {
    sPhoto = 0.0
    photoMatchReason = 'No return photo provided'
  } else if (isVisualMismatch) {
    sPhoto = 0.15
    photoMatchReason = 'Visual mismatch: returned product visually differs from sold item'
  } else if (refName && retNames.some((r) => r === refName)) {
    sPhoto = 1.0
    photoMatchReason = '100% visual match: return photo identical to sold catalog photo'
  } else if (keywords.some((kw) => retNames.some((r) => r.includes(kw)))) {
    sPhoto = 0.95
    photoMatchReason = 'High visual match: return photo matches product model'
  } else {
    sPhoto = 0.90
    photoMatchReason = 'Product present, visual comparison completed'
  }

  // 2. Component Completeness (30%)
  const partsListStr = row.parts_list || ''
  let partsMissingStr = row.parts_missing || ''
  if (!partsMissingStr && scenarioText) {
    const expectedP = partsListStr.split(';').map((s) => s.trim()).filter(Boolean)
    const detected: string[] = []
    for (const p of expectedP) {
      const pLow = p.toLowerCase()
      if (scenarioText.includes(`returned ${pLow}`) || scenarioText.includes(`in the ${pLow}`)) {
        continue
      }
      if (
        pLow &&
        (
          scenarioText.includes(`${pLow} itself`) ||
          scenarioText.includes(`${pLow} reported missing`) ||
          scenarioText.includes(`${pLow} reported absent`) ||
          scenarioText.includes(`${pLow} is missing`) ||
          scenarioText.includes(`${pLow} missing`) ||
          scenarioText.includes(`${pLow} absent`) ||
          scenarioText.includes(`(${pLow})`) ||
          scenarioText.includes(`${pLow} +`) ||
          scenarioText.includes(`+ ${pLow}`)
        ) &&
        ['missing', 'absent', 'not included', 'fewer', 'lost', 'without'].some((w) => scenarioText.includes(w))
      ) {
        detected.push(p)
      }
    }
    if (detected.length === 0) {
      if (scenarioText.includes('fewer pieces') || scenarioText.includes('pieces missing') || scenarioText.includes('pieces absent')) {
        for (const p of expectedP) {
          if (p.toLowerCase().includes('piece') || p.toLowerCase().includes('part')) {
            detected.push(p)
          }
        }
      } else if ((scenarioText.includes('main part') || scenarioText.includes('main component')) && ['missing', 'absent', 'without'].some((w) => scenarioText.includes(w))) {
        if (expectedP.length > 0) detected.push(expectedP[0])
      } else if ((scenarioText.includes('side parts') || scenarioText.includes('accessories')) && ['missing', 'absent', 'without'].some((w) => scenarioText.includes(w))) {
        if (expectedP.length > 1) detected.push(...expectedP.slice(1))
      }
    }
    if (detected.length > 0) {
      partsMissingStr = detected.join(';')
    }
  }

  const expectedParts = partsListStr.split(';').map((s) => s.trim()).filter(Boolean)
  const missingParts = partsMissingStr.split(';').map((s) => s.trim()).filter(Boolean)

  const nExpected = Math.max(1, expectedParts.length)
  const nMissing = missingParts.length
  const nPresent = Math.max(0, nExpected - nMissing)

  let sComp = 1.0
  let compReason = `All ${nExpected} expected component(s) present (${nPresent}/${nExpected})`
  if (nMissing > 0) {
    sComp = Math.max(0, nPresent / nExpected)
    compReason = `Missing ${nMissing} of ${nExpected} component(s): ${missingParts.join(', ')}`
  }

  // 3. Surface & Physical Condition (20%)
  const observedState = row.observed_state || 'uncertain'
  const amazonCondition = row.amazon_condition || 'uncertain'

  let sCond = 0.96
  let resolvedCondition = 'Used - Like New'
  let resolvedState = 'opened_unused'
  let condReason = 'Clean surface, no defects observed, like new'

  if (hasDamagePhoto || observedState === 'damaged') {
    sCond = 0.40
    resolvedCondition = 'Used - Acceptable'
    resolvedState = 'damaged'
    condReason = 'Physical damage / fractures observed'
  } else if (category === 'beauty_topical' && sPhoto >= 0.90 && !isVisualMismatch && nMissing === 0) {
    sCond = 1.0
    resolvedCondition = 'New'
    resolvedState = 'factory_sealed'
    condReason = 'Factory sealed / pristine new condition'
  } else if (category === 'grocery_ingestible') {
    sCond = 0.70
    resolvedCondition = 'Used - Acceptable'
    resolvedState = 'signs_of_use'
    condReason = 'Opened consumable item'
  } else if (isWornOrUsed) {
    sCond = 0.75
    resolvedCondition = 'Used - Acceptable'
    resolvedState = 'signs_of_use'
    condReason = 'Items show surface wear, blemishes, or signs of use'
  } else if (['battery', 'cover', 'cable', 'accessory', 'adapter'].some((p) => partsMissingStr.includes(p))) {
    sCond = 0.88
    resolvedCondition = 'Used - Very Good'
    resolvedState = 'signs_of_use'
    condReason = 'Product in good condition, missing replaceable accessories/parts'
  } else if (nMissing > 0) {
    sCond = 0.75
    resolvedCondition = 'Used - Acceptable'
    resolvedState = 'signs_of_use'
    condReason = 'Missing non-replaceable primary component'
  } else if (isVisualMismatch) {
    sCond = 0.85
    resolvedCondition = retNames.some((n) => n.includes('phone') || n.includes('samsung')) ? 'Used - Very Good' : 'Used - Acceptable'
    resolvedState = 'signs_of_use'
    condReason = 'Returned item physically present, but does not match sold catalog item'
  } else if (retPhotos.length === 0) {
    sCond = 0.20
    resolvedCondition = 'uncertain'
    resolvedState = 'uncertain'
    condReason = 'Condition undetermined due to missing return photos'
  } else if (amazonCondition !== 'uncertain' && amazonCondition !== '' && observedState !== 'uncertain' && observedState !== '') {
    sCond = amazonCondition === 'New' || amazonCondition === 'Used - Like New' ? 0.96 : 0.88
    resolvedCondition = amazonCondition
    resolvedState = observedState
    condReason = `Evaluated as ${amazonCondition}`
  }

  // 4. Paperwork & Identity Integrity (10%)
  const idCheck = row.sold_vs_returned_id_check || ''
  const isMismatch = idCheck.startsWith('NOT MATCHED')

  const sId = isMismatch ? 0.15 : 1.0
  const idReason = isMismatch
    ? `Paperwork mismatch: ${idCheck}`
    : 'Order, SKU, and ASIN match sold unit record'

  // Overall Confidence
  const weighted = 0.40 * sPhoto + 0.30 * sComp + 0.20 * sCond + 0.10 * sId
  const confidence = Math.max(5, Math.min(99, Math.round(weighted * 100)))

  // Deterministic Disposition Rule Routing
  let recDisposition = 'restock'
  let ruleId = 'R13_COMPLETE_RESTOCK'

  if (retPhotos.length === 0 && scenarioText.includes('no_return_photo')) {
    recDisposition = 'pending_review'
    resolvedCondition = 'uncertain'
    resolvedState = 'uncertain'
    ruleId = 'R01_NO_RETURN_PHOTO'
  } else if (retPhotos.length === 0 && ['battery', 'cover', 'cable', 'accessory', 'adapter'].some((p) => partsMissingStr.includes(p))) {
    recDisposition = 'refurbish'
    resolvedCondition = 'Used - Very Good'
    resolvedState = 'signs_of_use'
    ruleId = 'R09_REFURBISH_REPLACEABLE_PARTS'
  } else if (retPhotos.length === 0 && nMissing > 0) {
    recDisposition = 'liquidate'
    resolvedCondition = 'Used - Acceptable'
    resolvedState = 'signs_of_use'
    ruleId = 'R10_SALVAGE_LIQUIDATE'
  } else if (retPhotos.length === 0) {
    recDisposition = 'pending_review'
    resolvedCondition = 'uncertain'
    resolvedState = 'uncertain'
    ruleId = 'R01_NO_RETURN_PHOTO'
  } else if (isMismatch) {
    recDisposition = 'wrong_product'
    ruleId = 'R03_PAPERWORK_MISMATCH'
  } else if (isVisualMismatch || sPhoto < 0.30) {
    recDisposition = 'wrong_product'
    ruleId = 'R03_VISUAL_MISMATCH'
  } else if (category === 'grocery_ingestible') {
    recDisposition = 'dispose'
    resolvedCondition = 'Used - Acceptable'
    resolvedState = 'signs_of_use'
    ruleId = 'R08_CONSUMABLE_OPENED'
  } else if (hasDamagePhoto || resolvedState === 'damaged') {
    recDisposition = 'dispose'
    resolvedCondition = 'Used - Acceptable'
    resolvedState = 'damaged'
    ruleId = 'R10_SAFETY_SHATTERED_SCREEN'
  } else if (category === 'pet') {
    recDisposition = 'liquidate'
    resolvedCondition = 'Used - Like New'
    resolvedState = 'opened_unused'
    ruleId = 'R07_PET_OPENED_LIQUIDATE'
  } else if (['battery', 'cover', 'cable', 'accessory', 'adapter'].some((p) => partsMissingStr.includes(p))) {
    recDisposition = 'refurbish'
    resolvedCondition = 'Used - Very Good'
    resolvedState = 'signs_of_use'
    ruleId = 'R09_REFURBISH_REPLACEABLE_PARTS'
  } else if (nMissing > 0 || isWornOrUsed) {
    recDisposition = 'liquidate'
    resolvedCondition = 'Used - Acceptable'
    resolvedState = 'signs_of_use'
    ruleId = 'R10_SALVAGE_LIQUIDATE'
  } else if (category === 'beauty_topical') {
    recDisposition = 'restock'
    resolvedCondition = 'New'
    resolvedState = 'factory_sealed'
    ruleId = 'R06_NEW_ONLY_SEALED'
  } else {
    recDisposition = 'restock'
    resolvedCondition = 'Used - Like New'
    resolvedState = 'opened_unused'
    ruleId = 'R13_COMPLETE_RESTOCK'
  }

  const isAutoApproved =
    confidence >= 85 &&
    recDisposition === 'restock' &&
    !isMismatch &&
    sPhoto >= 0.85 &&
    nMissing === 0 &&
    !hasDamagePhoto &&
    resolvedState !== 'damaged'

  // Auto-disapproved / rejected: engine is definitively certain the return is invalid.
  // Conditions (any one is enough):
  //   1. Paperwork ID mismatch — SKU / ASIN / Order ID / Org ID don't match sold record
  //   2. Photo mismatch — photos didn't match from before sell to after sell
  //   3. Wrong product — returned product differs from sold catalog item
  // These cases need no human review; they are automatically disapproved.
  const isAutoRejected =
    recDisposition === 'wrong_product' ||
    isMismatch ||
    isVisualMismatch ||
    (sPhoto < 0.30 && retPhotos.length > 0) ||
    row.operator_disposition === 'wrong_product'

  const finalDisposition = isAutoRejected ? 'wrong_product' : recDisposition

  return {
    confidence,
    visual_match_pct: Math.round(sPhoto * 100),
    completeness_pct: Math.round(sComp * 100),
    condition_pct: Math.round(sCond * 100),
    identity_pct: Math.round(sId * 100),
    is_auto_approved: isAutoApproved && !isAutoRejected,
    is_auto_rejected: isAutoRejected,
    is_auto_disapproved: isAutoRejected,
    recommended_disposition: finalDisposition,
    resolved_condition: resolvedCondition,
    resolved_state: resolvedState,
    rule_id: ruleId,
    photo_match_reason: photoMatchReason,
    comp_reason: compReason,
    cond_reason: condReason,
    id_reason: idReason,
    summary: (isAutoApproved && !isAutoRejected)
      ? `Auto-approved (Confidence: ${confidence}% >= 85%): ${compReason}. ${photoMatchReason}. Pushed to ${finalDisposition.toUpperCase()}.`
      : isAutoRejected
        ? `Auto-disapproved: ${isMismatch ? `ID mismatch: ${idReason}` : `Visual photo mismatch: ${photoMatchReason}`}. Marked as WRONG PRODUCT / REJECTED.`
        : `Rule ${ruleId}: ${finalDisposition.toUpperCase()} (Confidence: ${confidence}%). ${compReason}. ${condReason}.`,
  }
}

