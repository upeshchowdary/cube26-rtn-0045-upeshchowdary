# FACTS.md — source of truth for the `ui-sydon` redesign

Every product claim, label, mockup value, navigation item, exception, audit step and FAQ answer on the
redesigned site must trace to a line in this file. If the redesign prompt conflicts with this file, this
file wins. Paths are relative to the repo root; `rm/` = `agent/src/returns_manager/`.

Written 2026-09-29 from the code on branch `upeshchowdary` @ `e34f26f`. `eval/sealed/` and `eval/labels/`
were not opened.

---

## 0. Conflicts and gaps found while writing this (need a decision before step 2)

| # | Issue | Evidence | Proposed handling |
|---|---|---|---|
| 0.1 | `dev check` can never be green on branch `ui-sydon`: its boundary check requires the branch to be named exactly `upeshchowdary`. On `ui-sydon` today: ruff, mypy, pytest (553 passed), reference validate all **ok**; boundary check **FAILED** only on the branch name. | `scripts/check_boundary.py`; run on 2026-09-29 | Report `dev check` as "all green except the branch-name boundary rule" each step, or you tell me to work on `upeshchowdary`. I will not weaken the check. |
| 0.2 | **No real, fully-inspected batch row exists on disk.** The only genuine run of the current runner (`./smoke-stage3/out_cli.csv`, outside the repo) failed open on every row (image fetch HTTP 403 / no return photo). `agent/manual_test_images/returns_output_30.csv` is an answer key, not output. `scratch/downloaded_output_*.csv` came from a deleted heuristic and contain the forbidden value `wrong_product`. | §10 | Every mockup is labelled **"Sample data"**. Each sample scenario is run through `disposition/engine.py` with current params before it goes on screen, so condition → route pairs are ones the engine really produces. |
| 0.3 | **No legally showable real product photos in the repo.** | §11 | Use the app's existing placeholder / neutral product silhouettes, labelled. Optionally the synthetic fixture diagrams (watermarked "SYNTHETIC TEST FIXTURE"). Wikimedia photos only if you want me to check and attribute each file's licence. |
| 0.4 | Auto-disapproval is now recorded by batch output as a separate boolean, not as a fifth disposition route. It is set only for a proven sold/returned ID mismatch or explicit model image-identity mismatch; uncertain evidence is not disapproval. | `rm/batch/runner.py` and `rm/batch/io_csv.py` | Show the Auto-disapproved outcome distinctly from the four disposition routes; keep uncertain/fail-open rows in review. |
| 0.5 | **Batch overrides don't store the original value.** The DB review service does (`rm.overrides.original_value`), but the batch decision log (the path the UI uses) records only `record_id, action, new_disposition, reason, actor, at`. | `rm/review/service.py:377-395`; `rm/batch/jobs_service.py:305-312` | Site copy says "overrides are recorded with the new value, the reason and who made it", and mentions the original value only for the inspection-review path. Alternatively add `original_disposition` to the batch decision entry, with a test (a backend change, so only with your OK). |
| 0.6 | The existing app contains **invented content**: "Northstar Goods / Enterprise workspace", "All systems operational 99.98%", "Operations Lead / Demo Operator", Catalogue captions claiming "real reference photo … exact before-sale photo URL" (it's the returned photo), Passport falling back to `rows[0]`, "Client Cache: Active & Ready", 3 hard-coded "Users & roles", the landing page's "RECOVERY VALUE $684", "REFUND / REJECT" badges, "ALL SYSTEMS OPERATIONAL · VERIFIED". | §1.2 | In step 4, remove or relabel these (they break Part B/J), without removing any working feature. Please confirm this is inside "change how they look". |
| 0.7 | The Sydon screenshots folder was never specified (`<SCREENSHOTS_FOLDER>` is still a placeholder) and no reference video was provided. | prompt A1 | I'll study sydon.ai live. Send the folder path if screenshots exist. |
| 0.9 | **Batch rows are not hash-chained.** The batch path (the UI's path) appends decisions to the job's append-only `decisions.json`; only the per-return inspection pipeline writes chain events. The app already says so (`ui/src/screens/Evidence.tsx:44-48`). | `rm/batch/jobs_service.py:289-315`; no `chain` import in `rm/batch/` | Audit-trail copy says the hash chain covers the inspection pipeline, and batch decisions go to an append-only decision log. Never claim a batch decision is hash-chained. |
| 0.8 | Old landing assets: `ui/public/frames/*.webp` (161 frames, 12 MB) carry a third-party **"FRAMEFLOW" watermark**. `final-world.jpg/.webp` has no recorded provenance. | §11 | Keep them on disk (per A1) but don't render them on the new page. |

---

## 1. Routes and screens (→ navigation)

All workspace routes are behind `Connect` (API-key login, which it validates by listing jobs). `/` redirects to `/overview`.
Source: `ui/src/App.tsx:497-541` (routes at lines 500-533; nav groups at 56-82).

| Route | Screen | Current nav label | What it really does | Data |
|---|---|---|---|---|
| `/overview` | `CinematicOverview.tsx` | (landing) | Scroll animation over 161 frames. **Replaced by the new landing page.** | hard-coded |
| (gate) | `Connect.tsx` | — | API-key login | real |
| `/dashboard` | `Dashboard.tsx` | Overview | 6 metric tiles, rows-per-upload chart, disposition donut, needs-attention list | real (store) |
| `/returns` | `Returns.tsx` | Returns | Paged table: tabs, search, sort, CSV download | real |
| `/returns/new` | `BatchUpload.tsx` | New inspection | CSV upload with spend-confirmation checkbox, then live job progress (polling) | real |
| `/returns/:id/inspection` | `Inspection.tsx` + `InspectionComparison.tsx` | — | Photo viewer, identity / parts / condition, rule ID, review reasons, accept / override / retake / review, decision history. Labels synthetic prices as such. | real |
| `/reviews` | `Reviews.tsx` | Review queue | Review queue + 4 counters (caption "No real pipeline run" on the uncertain card is misleading) | real |
| `/catalogue` | `Catalogue.tsx` | Product catalogue | One card per distinct SKU seen in batch rows | real counts, wrong photo caption |
| `/units/:id` | `Passport.tsx` | Unit passports | Unit timeline: upload → inspection → decision | real, bad fallback |
| `/evidence` | `Evidence.tsx` | Evidence & audit | Processed rows + hash-chain verification lookup by unit | real |
| `/analytics` | `Analytics.tsx` | Analytics | Condition bars, identity split, top missing parts, one backend metric (`uncertain_rate`) | real, "no data" when empty |
| `/integrations` | `Integrations.tsx` | Integrations | Static list of 5 pods; all but this one "Not connected" | static, honest |
| `/settings` | `Settings.tsx` | Settings | Kill switches, API keys create/revoke, clear cache | mostly real |

**Landing-page header links** may use: section anchors + Dashboard, Returns, New inspection, Review queue,
Evidence & audit (all real). Never Pricing / Plans / Billing.

### 1.2 Invented content currently in the UI (see 0.6)
`App.tsx:211-216` Northstar Goods / Enterprise workspace · `App.tsx:259` "All systems operational 99.98%" ·
`App.tsx:268-269` Operations Lead / Demo Operator · `App.tsx:285` breadcrumb · `CinematicOverview.tsx:560-566,64,714,42,56` ·
`Catalogue.tsx:18,58` · `Passport.tsx:10` · `Settings.tsx:204,321-327` · `Evidence.tsx:85-88` (verified icon when no decision).

---

## 2. Dispositions (exactly four)

`rm/disposition/engine.py:23`: `Route = Literal["restock", "refurbish", "liquidate", "dispose"]`.
Display labels: **Restock, Refurbish, Liquidate, Dispose.** Rank (`engine.py:24`): restock 3 > refurbish 2 > liquidate 1 > dispose 0.

- "No recommendation" is `None` (with a `no_recommendation_reason`), **not** a fifth route.
- In batch output, `operator_disposition` is one of the four routes or `pending_review`, which is a **status**
  (`rm/batch/runner.py:309-316`). Contract: `Outcome.decision` ∈ RESTOCK|REFURBISH|LIQUIDATE|DISPOSE|PENDING_REVIEW.

### 2.1 Rules (evaluated: review flags → gates → routes; first match wins)

**Gates**: no recommendation, `requires_review = true` (`engine.py:268-306`)

| Rule | Condition | `no_recommendation_reason` |
|---|---|---|
| R01b | inspection skipped | the skip reason, e.g. `no_product_reference` |
| R01 | inspection incomplete or 0 usable photos | `inspection_incomplete` |
| R02 | unit presence ≠ product_present | `item_not_present_or_unverified` |
| R03 | product identity = no | `wrong_item_returned` |
| R03b | product identity = uncertain | `identity_unverified` |
| R05b | no grade and no deciding blocker | `condition_uncertain` |

**Routes** (`engine.py:170-243`)

| Rule | Condition | Route |
|---|---|---|
| R06 | new-only category, grade New, no blockers | restock (as New) |
| R07 | new-only category, opened/damaged → category policy route | liquidate / dispose (restock/refurbish policy → R99 conflict) |
| R08 | consumable used | dispose |
| R09 | essential part missing, all replaceable, net gain ≥ ₹100, **and the complete item would route refurbish or better** (F-012) | refurbish |
| R10 | essential part missing and not refurbishable, or damaged / not clean | liquidate if liquidate recovery > ₹50, else dispose |
| R11 | functional test required | refurbish if net gain ≥ ₹100, else liquidate |
| R12 | grade New, no blockers | restock (as New) |
| R13 | grade in `restock_used_grades` and complete (or Used - Acceptable with only non-essential parts missing) | restock (as that grade) |
| R14 | used grade outside `restock_used_grades`, or non-essential parts missing where the rubric disallows | liquidate |
| R99 | nothing matched | none (`rule_gap` / `policy_conflict`) |

### 2.2 Current parameters (`reference/rules/disposition-params.yaml`)
- `restock_used_grades: [used_like_new, used_very_good]` (lines 3-5). **Used - Good and Used - Acceptable do not restock** (→ R14 liquidate, absent other blockers).
- `refurbish_min_net_gain` 10000 INR minor (₹100, :6-8) · `dispose_max_salvage` 5000 (₹50, :9-11) · `high_value_threshold` 500000 (₹5,000, :12-14).
- Currency is INR.

### 2.3 Category policy routes (`reference/policies/amazon.co.uk/*.yaml`), opened / damaged
electronics restock / liquidate · home_kitchen restock / dispose · toys_games restock / dispose ·
pet liquidate / dispose · beauty_topical dispose / dispose · grocery_ingestible dispose / dispose.

### 2.4 Review and sign-off (`engine.py:252-325`, `rm/review/service.py`)
- `requires_review = any review reason OR no route OR provisional`.
- **Sign-off (four-eyes)** only on a routed decision:
  - `S01_dispose_always`: route is dispose;
  - `S02_high_value`: route is not restock and list price ≥ ₹5,000;
  - `S03_escalation_disagreement_resolved`.
- After overrides, an effective disposition of dispose always needs sign-off (`review/service.py:451`).
- The capturer / batch uploader cannot sign off their own return (`review/service.py:280-281`, `batch/jobs_service.py:296-304`).

---

## 3. Amazon condition grades

Codes `new, used_like_new, used_very_good, used_good, used_acceptable` (`rm/llm/schemas.py:98`). Labels exactly:
**New · Used - Like New · Used - Very Good · Used - Good · Used - Acceptable**
(`reference/rubrics/amazon.co.uk/electronics.yaml:16,22,27,32,38`).

- beauty_topical, grocery_ingestible and pet rubrics allow **New only**.
- If no grade is available: `amazon_condition = "uncertain"` (`rm/judgment/grading.py:74`).
- `functional_check` is always `"not_performed"`.
- Rubric snapshots: `amazon-uk-condition-guidelines-2020-12-<category>` (`reference/rubrics/active.yaml`). Every file has
  `verification_status: unverified_substitute`: source marketplace amazon.co.uk, applied to amazon.in (ADR-006, F-001).
  - Required wording: "Graded against Amazon's published condition guidelines (unverified substitute snapshot)".
- Listing blockers: essential_component_missing, damaged_difficult_to_use, not_clean, functional_test_required,
  category_new_only_opened, consumable_used (`rm/judgment/types.py:21-28`).
  - A blocker the photos can't settle goes to `blockers_undetermined` and is never assumed absent.

## 4. `observed_state`

`factory_sealed · opened_unused · signs_of_use · damaged · empty_box · uncertain` (`rm/llm/schemas.py:99-101`).
Display: Factory sealed · Opened, unused · Signs of use · Damaged · Empty box · Uncertain.
`factory_sealed` is downgraded to `uncertain` unless packaging is `factory_sealed_intact` (`judgment/consistency.py:178`).

## 5. Exceptions: `review_reasons` and `no_recommendation_reason` codes

These are the **only** exceptions the site may show. The code has no human-readable labels, so the labels
below are proposed; the site shows the label with the code nearby.

| Code | Proposed label | Source |
|---|---|---|
| `inspection_incomplete` | Inspection incomplete | engine R01 |
| `item_not_present_or_unverified` | Product not confirmed in photos | engine R02 |
| `wrong_item_returned` | Identity mismatch: possible product swap, requires review | engine R03 |
| `identity_unverified` | Product identity uncertain | engine R03b |
| `condition_uncertain` | Condition uncertain | engine R05b |
| `no_product_reference` | No product reference on file | skip, `llm/context.py:200-224` |
| `no_category_mapping` / `no_rubric_for_category` / `no_policy_for_category` | No category mapping / rubric / policy | skip |
| `assisted_mode` | Assisted mode: auto-disposition off | engine R00 |
| `essential_component_uncertain` | Essential part not visible in the provided photos | engine R05 (treated as missing, provisional) |
| `nonessential_component_uncertain` | Non-essential part not visible in the provided photos | engine R05c |
| `listing_blockers_undetermined` | Listing blockers undetermined | engine R05c |
| `rule_gap` / `policy_conflict` | No rule matched / Policy conflict | engine R99 |
| `injection_attempt_suspected` | Instruction-like text found in photos | C14 `judgment/consistency.py:184` |
| `possible_reused_photo` | Possible reused photo | `intake/quality.py:199` |
| `model_disagreement` | Re-inspection disagreed | `inspection/service.py:569` |
| `escalation_triggered` | Escalated for a second inspection | `judgment/pipeline.py:391` |
| `photo_quality_acknowledged` | Photo quality issue acknowledged | `judgment/pipeline.py:393` |
| `signoff_rejected` | Sign-off rejected | `review/service.py:310` |
| `audit_disagreement` | (listed in `REVIEW_FLAGS`, but no code path produces it: **don't show**) | — |

- **Batch-only fail-open codes** go in `failure_reason`, not review reasons: `no_before_record, no_reference_photo,
  no_return_photo, no_category, unknown_category:<c>, reference_load_failed, image_fetch_failed, model_call_failed,
  max_requests_reached` (`batch/runner.py:437-533`).
- **Escalation triggers** (recorded separately): identity_conflict, essential_component_uncertain,
  high_value_condition_uncertain, possible_product_swap, injection_attempt_suspected, unit_presence_uncertain,
  operator_model_strong_disagreement.

## 6. Audit trail: chain event types (`rm/chain/event_types.py`)

**Unit event chain (28)** (`rm/chain/event_types.py:12-39`, one constant per line in this order): return_created, photo_received, photo_quality_assessed, photo_superseded,
operator_observation_recorded, return_submitted, job_enqueued, inspection_started, context_assembled,
model_request_completed, model_tool_executed, model_refusal, inspection_failed, inspection_skipped,
inspection_completed, validator_applied, identity_fused, escalation_requested, escalation_completed,
audit_completed, retake_requested, disposition_computed, operator_decision_recorded, override_recorded,
review_resolution_recorded, signoff_recorded, record_finalized, record_superseded.

**Org ledger (5)** (`event_types.py:42-46`): control_changed, key_issued, key_revoked, circuit_opened, circuit_closed.

- Each unit event carries `occurred_at`, `actor_type` + `actor_id`, `event_type`, `payload_sha256`, `prev_event_hash`, `event_hash`.
  - `event_hash = SHA-256("rm/evt/v1" ‖ 0x00 ‖ prev_event_hash ‖ JCS(core))` (`chain/crypto.py:82-88`).
- Ledger entries have **no actor**.
- Suggested timeline for the landing page (a real sequence, labelled Sample data): return_created → photo_received →
  photo_quality_assessed → inspection_started → inspection_completed → identity_fused → disposition_computed →
  operator_decision_recorded → signoff_recorded → record_finalized.
- **Wording** (ADR-007:12): "Tamper-evident within this database … Not immutable. Weakly anchored: ledger heads are
  published in public git commits." Short form already in the UI (`Evidence.tsx:165`): "Tamper-evident within the
  database (hash-chained); not immutable."

## 7. Metrics the app actually computes

**Dashboard (store only, no `/metrics` call; `Dashboard.tsx:90-95`):**
- Tiles: Total returns · Auto-approved · Auto-disapproved (UI filter, see 0.4) · Needs attention · Restock eligible ·
  Live model requests ("Real Gemini quota spent").
- Charts: rows per upload, disposition mix donut.

**`ui/src/lib/derive.ts`:** dispositionMix (:30), identityDistribution (:41; Matched / Uncertain / Mismatch), conditionDistribution (:61),
topMissingComponents (:70; top 6), rowsPerJob (:83), needsAttention (:95), reviewQueue (:99), distinctSkus (:103).

**`GET /api/v1/metrics/summary?window=24h|7d|30d|all`** (`rm/api/routes/metrics.py:57-72`, `rm/observability/metrics.py:456-475`): each metric is `{value, n, window, method}`.
- Keys: throughput_per_hour, model_latency_ms, queue_wait_ms, capture_to_decision_ms, requests_per_inspection,
  tool_calls_per_inspection, tokens_per_inspection, uncertain_rate, retake_rate, escalation_rate,
  audit_disagreement_rate, override_rate, signoff_approval_rate, needs_attention_rate, error_rate_by_class,
  disposition_distribution, integrity_counters.
- The UI displays **only `uncertain_rate`** (`ui/src/screens/Analytics.tsx:27,110-112`). `/metrics/economics` exists; no screen calls it.

**No metric values may appear on the landing page except as "Sample data".**

## 8. AI prose summary

- **The batch pipeline writes no prose summary.** No summary column in the CSV and no narrative field in row detail
  (`batch/runner.py:151-185`).
- The model's output has only short capped fields (evidence observation, defect location note, retake instruction,
  uncertainty detail).
- The **explainer** (`POST /api/v1/units/{unit_id}/explain`, also an MCP tool) is on-demand and **deterministic keyword
  templating over the stored evidence, not an LLM call** (`rm/explainer/service.py`). It cites evidence paths, and answers
  "This is not recorded in the evidence for this unit" otherwise.
- **The UI never calls it.**
- → The site must not show an AI summary as routine output. E7 shows structured check results only.

## 9. Auto-approve (`rm/batch/auto_approve.py:43-71`)

A batch row is auto-approved only if **none** of these block it:
- `no_recommendation`, `requires_review`, `requires_signoff` (so dispose and high-value rows are never auto-approved);
- `escalation_triggered`, `sold_vs_returned_id_mismatch`, `sold_vs_returned_id_not_checked`;
- `no_checks`, `check_not_passed` (every check must be PASS), `confidence_below_threshold`.

**Threshold:** lowest check confidence ≥ **8500 bp** (`rm/config.py:105`, `RM_BATCH_AUTO_APPROVE_MIN_CONFIDENCE_BP`).
**"NOT yet calibrated by a threshold sweep (§21.5); 8500 is a placeholder, not a measured operating point"**
(`config.py:103-104`); the result records `threshold_calibrated: false`.

Approval never changes the route; it only lets `operator_disposition` equal the engine's route.
Auto-approval also requires `photo_identity_match=yes` and no observed damage. A confirmed ID or photo mismatch is recorded in `auto_disapproved`; it is an outcome flag, not a fifth disposition route. Missing or uncertain evidence remains pending review.

## 9b. Identity, parts, decisions (supporting facts)

- **Product identity (photo)**, `photo_identity_match`: yes / no / uncertain, fused by `rm/judgment/fusion.py:67-134`.
  - Only critical features on the product body count; feature results are match / mismatch / not_visible.
  - Model yes + no barcode → yes (moderate) only with ≥ 2 matched critical body features, else uncertain.
  - Barcode matches ordered + model yes → yes (strong). Barcode matches ordered + model no → uncertain + `possible_product_swap`.
  - **A barcode alone never produces yes.**
  - Barcode status: matches_ordered / matches_other_sku / unknown_code / none_decoded / conflicting.
- **Sold vs returned records**, `sold_vs_returned_id_check` (`batch/runner.py:197-227`): compares org_id, order_id,
  ordered_sku, ordered_asin.
  - Values: `matched` · `NOT MATCHED: <field>: sold=… vs returned=…` · `not checked: <field> missing` ·
    `NOT MATCHED: no sold-record for this unit_id`.
- `identity_match` (CSV) is carried forward from the before-file and never re-derived (F-024). **Two separate checks; never merge them.**
- **Parts:** component status present / missing / uncertain.
  - Model visibility: observed_present / observed_absent_in_clear_view / not_visible / conflicting.
  - Completeness: complete / incomplete / uncertain. A part with unknown `essential` counts as essential.
  - CSV `parts_missing` holds both missing and uncertain parts.
- **Decisions (batch, what the UI uses)** (`rm/api/routes/batch.py:376`, `rm/batch/jobs_service.py:41,289-315`): accept · override (needs `new_disposition` + reason) · retake_request
  (recorded; doesn't change the CSV) · review_request (back to pending_review).
  - Rows needing sign-off need the SIGNOFF permission.
- **Decisions (inspection review service):** accept / override (fields: identity_match, unit_presence, cosmetic_grade,
  amazon_condition, disposition, component status), resolve review, sign-off approve / reject.
  - Override reason codes: missed_defect, false_defect, occluded_component, similar_sku, packaging_state_misread,
    barcode_misread, policy_exception, photo_quality, other.
  - Each override records original value, new value, reason, actor, role, plus an `override_recorded` chain event.
  - "Overrides are recorded as labelled data; no automatic retraining."
- **Batch output columns** (`batch/io_csv.py:214-235`): record_id, unit_id, org_id, order_id, ordered_sku,
  ordered_asin, identity_match, photo_identity_match, parts_list, parts_missing, observed_state, amazon_condition,
  operator_disposition, agent_disposition, auto_approved, auto_disapproved, photo_refs, captured_at, sold_vs_returned_id_check,
  failure_reason, value_source.
- **Field labels for step 4:** ordered_sku → Ordered SKU · ordered_asin → Ordered ASIN · identity_match → Identity (sold record) ·
  photo_identity_match → Product identity (photo) · parts_missing → Missing parts · observed_state → Observed state ·
  amazon_condition → Amazon condition · agent_disposition → Recommended disposition · operator_disposition →
  Final disposition · sold_vs_returned_id_check → Sold vs returned records · failure_reason → Fail-open reason ·
  value_source → Value source.

## 10. Rows for mockups

No fully-inspected real row exists (see 0.2). Candidates, with their status:

**A. Clean row: answer key, not output** (`agent/manual_test_images/returns_output_30.csv:8`)
- RTN-PHONE-01 · UNIT-PHONE-01 · ORD-PHONE-01 · SKU-PHONE-A · B0PHONE01, electronics.
- Parts: handset; battery; battery cover. None missing.
- opened_unused · Used - Like New · restock · records matched.
- Engine-consistent (R13: Used - Like New ∈ restock_used_grades, complete), **if** no functional-test blocker applies.
  I'll verify against the engine before use.
- The real run of the same record failed open: `image_fetch_failed … HTTP 403` (`smoke-stage3/out_cli.csv:2`).

**B. Missing part: answer key** (`returns_output_30.csv:9`)
- RTN-PHONE-02: parts missing battery; battery cover · signs_of_use · Used - Very Good · refurbish.
- It has no return photo, so the real runner gives `no_return_photo` → pending_review. **Not usable as-is.**
- Alternative: `agent/contract/examples/rtn-example-001-refurbish.json` (illustrative, placeholder hashes):
  SKU-BT-HEADPHONES, "usb charging cable" missing, Used - Good, R09 refurbish.
  - Under the current engine R09 needs the complete item to route refurbish or better. That requires the
    functional_test_required blocker (→ R11), which the example does not list. **Treat as illustrative; re-derive with the engine.**

**C. Uncertain: genuine run output** (`./smoke-stage3/out_cli.csv:4`)
- RTN-AIR-02 · UNIT-AIR-02 · ORD-AIR-02 · SKU-AIR-A · B0AIR001.
- Parts: AirPods case · identity_match yes · photo_identity_match uncertain · observed_state uncertain · amazon_condition uncertain · pending_review.
- Records matched. failure_reason image_fetch_failed (HTTP 403).
- It's a deliberate phone-for-AirPods photo swap that never reached the model.

**Plan:** build 3 "Sample data" scenarios on these IDs' shape (clean restock; missing replaceable essential part →
refurbish; identity uncertain → no recommendation, review). Run each through `disposition/engine.py` with current
params in a scratch script, and put only the engine's actual output (route, rule ID, review reasons, sign-off) on screen.

**Real reference card with a replaceable essential part:** SKU-LAMP-LED "LED desk lamp with USB cable"
(electronics): lamp (essential), usb cable (essential, replaceable), manual (non-essential).
Critical features: round weighted matte-black base about 12 cm; touch switch on the arm. This matches the problem
statement's "USB cable missing" example. The card is marked SYNTHETIC placeholder.

## 11. Photos

| Asset | Can show? |
|---|---|
| `fixtures/returns_dataset_v1/images/*.jpg` (10), Pillow-drawn and watermarked "SYNTHETIC TEST FIXTURE — NOT REAL PRODUCT EVIDENCE" | Yes, as labelled synthetic diagrams only |
| `reference/products/org_demo_alpha/SKU-PHONE-IQOO9/ref_contents.jpg` (third-party watermark) | **No** |
| `reference/products/org_demo_alpha/SKU-LAPTOP-DELL/ref_contents.jpg` (Google Images screenshot) | **No** |
| Wikimedia Commons URLs in `manual_test_images/returns_input_30.csv` (remote, no per-file licence recorded) | Only after a per-file licence check + attribution |
| `ui/public/frames/*.webp` ("FRAMEFLOW" watermark) | **No** (kept on disk) |
| `ui/public/final-world.*`, `ui/src/assets/hero.png` | No provenance / template default: **don't use** |

## 12. Other facts the copy may use

- **Mission** (CLAUDE.md): from 2–3 phone photos plus the seller's catalogue, order, parts list and Amazon's published
  condition guidelines, record an evidence-backed verdict on identity, completeness and condition. Deterministic rules
  (never the model) compute one of four dispositions, with "uncertain" and human review as first-class outcomes.
- **The model has no disposition field in its output**; every component, feature, grade, rubric quote and photo alias
  it references is checked by code.
- **Fail open:** a model/provider failure leaves the return pending / needs-attention with a reason, never a pass or a guessed grade.
- **Batch spend guard:** the upload screen needs an explicit spend confirmation. `--max-requests` caps real model requests.
- **Tenancy:** row-level security forced per org. Photos only via short-TTL signed URLs.
- **No contact info, company details, customers, integrations, pricing or testimonials exist.**
  - The footer gets no "Get in touch" line.
  - Integrations screen: the other pods (Receiving, Prep, Pack, Recovery) are "not built yet".
- **Forbidden vocabulary** (CLAUDE.md §24) applies on top of prompt Part J.

## 13. Self-check against Part B, and where the master prompt is contradicted (FACTS.md wins)

Part B check (2026-09-29): every disposition (§2), grade (§3), observed_state (§4), review code (§5), event type (§6),
route (§1), metric (§7) and the auto-approve rule (§9) above is quoted from code with file:line.

| Master prompt says | Code says | Follow |
|---|---|---|
| A1: keep `dev check` green | Boundary check fails on any branch not named `upeshchowdary` | All other gates green; branch rule reported (0.1) |
| E8: "overrides are recorded with the original value, the new value and the reason" | True for the inspection review service; batch overrides record new value, reason, actor and time, **not** the original | Copy per 0.5 |
| E10 / D4 Q8: "Every inspection leaves a trail", "Is every decision recorded?" | Hash chain covers the inspection pipeline only; batch decisions go to an append-only `decisions.json` | Copy per 0.9 |
| G: "the Auto-approved and Auto-disapproved views" | Auto-disapprove is a UI filter; no backend logic | Keep the view, relabel honestly (0.4) |
| G: "accept / override / retake / review decisions" | `retake_request` is recorded but changes nothing in the output CSV | Keep; don't describe it as triggering a re-capture |
| E4: result "Records match" or "Records don't match" | A third state exists: `not checked: <field> missing` | Show all three |
| A3.10 / E1: "real rows from an existing batch job" | None exists with a completed inspection (0.2) | Engine-verified "Sample data" |
| A3.11 / E6: "real product photos" | None legally showable (0.3, §11) | Labelled placeholders |
| E6: "defects observed (type, severity, location)" | The model reports defects with a location note (`llm/schemas.py:225`); the batch CSV has no defect column, only row detail | Show from row-detail shape, labelled Sample data |
| D5: "Get in touch" line | No contact info exists | Omit |
| E1 eyebrow / hero | — | No conflict |
