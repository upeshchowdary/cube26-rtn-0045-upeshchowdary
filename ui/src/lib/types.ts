// Shapes returned by the real backend (agent/src/returns_manager/api/routes/batch.py,
// metrics.py, security.py) - kept in sync with those routes, never invented.

export type BatchJobStatus = 'queued' | 'processing' | 'done' | 'failed'

export interface BatchJob {
  job_id: string
  org_id: string
  status: BatchJobStatus
  created_at: number
  before_filename: string
  returned_filename: string
  total_rows: number
  processed: number
  uncertain: number
  live_requests: number
  error: string | null
  notes: string[]
}

// The 20 flat columns written by batch/io_csv.py:OUTPUT_FIELDNAMES.
export interface BatchRowFlat {
  record_id: string
  unit_id: string
  org_id: string
  order_id: string
  ordered_sku: string
  ordered_asin: string
  identity_match: string // carried forward from the before-file (F-024)
  photo_identity_match: string // the model's own verdict on the returned photo(s)
  parts_list: string
  parts_missing: string
  observed_state: string
  amazon_condition: string
  operator_disposition: string // the engine route only if auto-approved; otherwise pending_review
  agent_disposition: string // the engine's recommendation ('' when it made none)
  auto_approved: string // 'true' | 'false' - decided by the backend (batch/auto_approve.py)
  photo_refs: string
  captured_at: string
  sold_vs_returned_id_check: string
  failure_reason: string // why the row failed open; empty on a real model + engine result
  value_source: string // 'csv_list_price' | 'synthetic_default' ('' when there is no before-record)
}

export type DecisionAction = 'accept' | 'override' | 'retake_request' | 'review_request'

export interface RowDecisionEntry {
  record_id: string
  action: DecisionAction
  new_disposition: string | null
  reason: string
  actor: string
  at: number
}

export interface CheckEntry {
  check_key: string
  verdict: 'PASS' | 'FAIL' | 'UNCERTAIN'
  confidence_bp: number
  detail: string
  source: 'model' | 'deterministic'
}

export interface EvidenceRefJson {
  photo: string
  box_2d: [number, number, number, number] | null
  observation: string
}

export interface DefectObservationJson {
  defect_type: string
  severity: 'minor' | 'moderate' | 'severe'
  location_note: string
  photo: string
  box_2d: [number, number, number, number] | null
  confidence: number
}

export interface PhotoReportJson {
  photo: string
  usable: boolean
  views: string[]
  visible_regions: string[]
  issues: string[]
}

// The raw judgment/v1 model output (see llm/schemas.py:JudgmentV1) - typed loosely on
// purpose for the parts the UI doesn't need to bind to individually.
export interface JudgmentJson {
  schema_version: string
  photo_reports: PhotoReportJson[]
  unit_presence: { status: string; evidence: EvidenceRefJson[] }
  identity: {
    identity_match: string
    observed_identifiers: Array<{ kind: string; value: string; photo: string; location: string }>
    feature_checks: Array<{ feature_id: string; result: string; photo: string | null }>
    risk_flags: string[]
    likely_actual_sku: string | null
    uncertainty_reason: string | null
    confidence: number
    evidence: EvidenceRefJson[]
  }
  completeness: {
    components: Array<{
      component_id: string
      observed_quantity: number | null
      visibility: string
      status: string
      photos: string[]
      confidence: number
    }>
    unexpected_items: Array<{ description: string; photo: string }>
    uncertainty_reason: string | null
  }
  condition: {
    packaging_state: string
    observations: DefectObservationJson[]
    signs_of_use: string
    cleanliness: string
    outer_shipping_damage_observed: boolean | null
    functional_check: string
    proposed_grade: {
      grade_code: string | null
      rubric_phrases_matched: string[]
      uncertainty_reason: string | null
      confidence: number
    }
  }
  model_observed_state: string
  retake_requests: Array<{ target: string; reason: string; instruction: string }>
  uncertainties: Array<{ area: string; reason: string; detail: string }>
  untrusted_text_observed: Array<{ photo: string; text: string }>
}

export interface ComponentResultJson {
  component_id: string
  name: string
  expected: number
  observed: number | null
  status: 'present' | 'missing' | 'uncertain'
  essential: boolean | null
  replaceable: boolean | null
  verifiable_by_photo: boolean
  missing_quantity: number
  photos: string[]
  confidence_bp: number
  reason: string | null
}

export interface RowDetail {
  judgment: JudgmentJson
  judgment_raw: JudgmentJson
  validator_actions: Array<{ rule_id: string; target: string; before: string; after: string; reason: string }>
  checks: CheckEntry[]
  presence: { status: string; clearly_evidenced: boolean; evidence_photos: string[] }
  identity: {
    identity_match: string
    strength: string
    barcode_status: string
    risk_flags: string[]
    reasons: string[]
    actual_sku: string | null
    confidence_bp: number
    evidence_photos: string[]
  }
  completeness: {
    status: string
    components: ComponentResultJson[]
    essential_missing: string[]
    nonessential_missing: string[]
    uncertain_components: string[]
    essential_uncertain: string[]
    parts_list: string
    parts_missing: string
    parts_uncertain: string
    flags: string[]
  }
  condition: {
    cosmetic_grade: string | null
    amazon_condition: string
    listing_blockers: string[]
    blockers_undetermined: string[]
    relistable_as_is: boolean | null
    packaging_state: string
    signs_of_use: string
    cleanliness: string
    max_severity: string
    phrases_matched: string[]
    confidence_bp: number
    uncertainty_reason: string | null
    functional_check: string
  }
  claims: {
    item_not_returned: { value: string; basis: string[]; evidence: string[] }
    wrong_item_returned: { value: string; basis: string[]; evidence: string[] }
    returned_damaged: { value: string; basis: string[]; evidence: string[] }
    parts_missing: string[]
    parts_uncertain: string[]
  }
  decision: {
    recommended_disposition: string | null
    no_recommendation_reason: string | null
    provisional: boolean
    assumptions: string[]
    requires_review: boolean
    review_reasons: string[]
    listing_condition: string | null
    rule_id: string
    rules_version: string
    reasons: string[]
    requires_signoff: boolean
    signoff_reasons: string[]
    expected_recovery_minor: Array<[string, number]>
    inputs_sha256: string
    decided_by: string
    synthetic_values: boolean
    currency: string
    extra: Record<string, string>
  }
  escalation_triggers: string[]
  requires_review: boolean
  review_reasons: string[]
  returned_photo_refs: string[]
  reference_photo_ref: string
  auto_approval?: {
    approved: boolean
    min_confidence_bp: number | null // lowest model-reported check confidence
    threshold_bp: number
    threshold_calibrated: boolean // false until the §21.5 threshold sweep is run
    blocked_by: string[]
  }
  // Where the numbers behind a value-driven outcome came from (batch/runner.py:value_record).
  value?: {
    list_price_minor: number
    currency: string
    value_source: string // 'csv_list_price' | 'synthetic_default'
    recovery_rates_source: string
    refurbish_cost_source: string
    value_driven_outcomes: string[] // e.g. ['R09'], ['S02_high_value'] - backend-computed
  }
}

export interface MetricEnvelope {
  value: unknown
  n: number
  window: string
  method: string
}

export interface MetricsSummaryResponse {
  window: string
  metrics: Record<string, MetricEnvelope>
}

export interface EconomicsReportResponse {
  window: string
  volume: number
  cost_by_stage: Record<string, MetricEnvelope>
  cost_per_inspection: MetricEnvelope
  projected_monthly_cost: MetricEnvelope
  recovery_uplift: MetricEnvelope
  sanity_anchor: Record<string, unknown>
}

export interface ControlOut {
  control: string
  enabled: boolean
  global_enabled: boolean | null
  org_enabled: boolean | null
  reason: string | null
  updated_by: string | null
  updated_at: string | null
}

export interface ControlsResponse {
  org_id: string
  controls: ControlOut[]
}

export interface KeyCreated {
  key_id: string
  api_key: string
  key_prefix: string
  org_id: string
  scopes: string[]
}

export interface ChainVerificationResponse {
  org_id: string
  unit_id: string
  valid: boolean
  units_checked: number
  events_checked: number
  ledger_entries_checked: number
  records_checked: number
  anchors_checked: number
  first_hash: string | null
  last_hash: string | null
  failures: string[]
  summary: string
}

// One row of the UI's own derived, per-row view - a BatchRowFlat plus its job/decision
// context. This is what every screen (Dashboard/Returns/Reviews/Inspection/...) consumes,
// replacing the old hardcoded `RecordRow`.
export interface DerivedRow extends BatchRowFlat {
  job_id: string
  job_status: BatchJobStatus
  job_created_at: number
  image: string | null // first returned photo URL for this exact row, or null
  reference_image: string | null // the before-row's own catalogue/reference photo URL
  photos: string[] // every returned photo URL for this row
  status: string // display status derived from job status + decisions
  // Review flag, never a disposition: the model saw a different item on the returned photo,
  // or the returned record's IDs disagree with the sold record.
  wrong_item_flag: boolean
  latest_decision: RowDecisionEntry | null
}
