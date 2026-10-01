# Architecture: Returns Manager (Cube Buildathon 04)

This document describes what is implemented in this repository: the data flow, the service
boundaries, the design decisions and the known gaps. Every claim points at the code, a test, or
`build-log.md` / `decisions/`. Where something is not done yet, it says so (section 6).

## Phase 6 status snapshot (2026-09-30)

- Current validation is green: `uv run returns-manager dev check` exited successfully on 2026-09-30, and the unit suite is currently `558 passed` with `5 warnings`.
- Smoke run, not an eval: the stored batch job metadata recorded `total_rows=4`, `uncertain=4`, `live_requests=2`, with notes for `quota_exhausted` and `no_return_photo`; it is a wiring smoke test, not a performance or accuracy result.
- The remaining honest gaps are still documented: no sealed eval set, no threshold calibration, no Recovery-pod contract agreement, and no benchmark that claims real 3D performance for the redesign.

## 1. What the agent does

From 2-3 phone photos of a returned product plus the seller's catalogue, order record, parts list
and Amazon's published condition guidelines, the agent records evidence for four questions:

```
Returned item
     │
     ▼
1. Identity      - is this the SKU/ASIN that was ordered?        (yes / no / uncertain)
     │
     ▼
2. Completeness  - are the expected parts present?               (per part: present / missing / uncertain)
     │
     ▼
3. Condition     - which of the five Amazon grades applies?       (New, Used - Like New, Used - Very Good,
     │                                                              Used - Good, Used - Acceptable, or uncertain)
     ▼
4. Disposition   - restock / refurbish / liquidate / dispose, or no recommendation (held for review)
     │
     ▼
Evidence record (identity + completeness + condition + disposition, with the photos and reasons behind each)
```

- **Grades:** only the five Amazon grades exist in code (`llm/schemas.py` `GradeCode`,
  `reference/models.py` `RubricGradeCode`, `review/merge.py`). `uncertain` is a verdict with a reason
  code, not a grade.
- **Dispositions:** only the four routes exist (`disposition/engine.py` `Route`). When the engine cannot
  recommend one, the recommendation is `null` with a `no_recommendation_reason`, and the row's
  `operator_disposition` is `pending_review` until a person decides. A wrong item is gate R03
  (`wrong_item_returned`): no recommendation and `auto_disapproved=true`, never a fifth disposition.
- **Batch auto-approval** additionally requires a positive image identity match and no observed damage.
  Proven ID or image-identity mismatches are separately marked `auto_disapproved`; the four disposition
  routes remain unchanged.
- **The model never decides the disposition.** The model's output schema (`llm/schemas.py` `JudgmentV1`)
  has no disposition field. The rules engine computes the disposition from the inspection evidence, the
  category policy and the product card.

## 2. Two ways to run it

### 2.1 The database-backed system

A FastAPI HTTP API, a durable job queue and Postgres (local Supabase), with tenancy enforced by
row-level security.

```
                         ┌─────────────────────────────────────────────┐
                         │              FastAPI (api/app.py)            │
                         │  /health  /ready                             │
                         │  security · intake · jobs · simulate ·       │
                         │  review · chain · evidence · explainer ·     │
                         │  webhooks · metrics · batch  (routers)       │
                         └───────────────────┬─────────────────────────┘
                                              │ HTTP
                                              ▼
   ┌───────────┐    photos + return record    ┌─────────────────┐
   │  Seller /  │ ─────────────────────────────▶│  intake          │
   │  operator  │                               │  images.py:      │
   └───────────┘                               │  sniff, decode,  │
                                                 │  preprocess      │
                                                 └────────┬─────────┘
                                                          │ stored before any model call
                                                          ▼
                                            ┌─────────────────────────┐
                                            │  rm.* tables (Postgres)  │
                                            │  RLS forced per org_id   │
                                            └────────────┬─────────────┘
                                                          │ enqueued job
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  jobs/worker.py             │
                                          │  kill switch → circuit      │
                                          │  breaker → daily quota →    │
                                          │  handler                    │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  inspection/service.py      │
                                          │  JudgmentHandler: assembles │
                                          │  the context bundle, calls  │
                                          │  llm/loop.py                │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  Gemini Interactions API    │
                                          │  (llm/gemini_client.py)     │
                                          │  one stateful session,      │
                                          │  chained via                │
                                          │  previous_interaction_id    │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  judgment/*.py              │
                                          │  fuse_identity, consistency │
                                          │  rules, claims              │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  disposition/engine.py      │
                                          │  deterministic rules (§3)   │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  contract/*.py              │
                                          │  evidence record + flat     │
                                          │  view, hash-chained per unit│
                                          └────────────────────────────┘
```

Migrations live in `agent/migrations/` (`0001_roles_and_schema.sql` … `0011_webhook_persistence.sql`,
11 files). `supabase/` holds only the local Supabase `config.toml`.

```sh
cd agent
uv sync
npx supabase start          # Docker Desktop must be running
uv run returns-manager db migrate
uv run returns-manager seed demo
uv run returns-manager dev check     # ruff + mypy + pytest (non-live) + reference validate + boundary check
uv run returns-manager worker        # process the job queue
uv run returns-manager api serve     # the HTTP API
```

### 2.2 The standalone batch tool (no database)

`batch/` runs the same judgment session (`llm/loop.run_session`) and the same deterministic pipeline
(`judgment/pipeline.run_pipeline` → `disposition/engine.decide`) on a CSV of image URLs, without
Postgres, RLS, the job queue or persistence. It makes real Gemini calls, so it needs an API key and
`--max-requests` (CLI) or `confirm_spend` (API) as its spend guard.

```
before.csv   (sold record: record_id, unit_id, org_id, order_id, ordered_sku, ordered_asin,
              identity_match, parts_list, time, photo_ref[, category][, list_price | list_price_minor])
returned.csv (returned record: record_id, unit_id, org_id, order_id, ordered_sku, ordered_asin,
              returned_photo_ref, time)
     │                                  │
     └──────────────┬───────────────────┘
                     │ joined on unit_id
                     ▼
        batch/runner.py: process_returned_row()
                     │
      ┌──────────────┼───────────────────────────────┐
      ▼              ▼                                ▼
 fetch photos    synthesize a product card    compare sold-vs-returned IDs
 (images.py)     (cards.py) from parts_list   (check_id_match), independent
                 and list price               of the photos
      │              │                                │
      └──────────────┴────────────────┬───────────────┘
                                       ▼
                        llm/loop.run_session (same code path as 2.1)
                                       ▼
                        judgment/pipeline.run_pipeline → disposition/engine.decide
                                       ▼
                        batch/auto_approve.evaluate (a flag, never an override)
                                       ▼
                        output.csv + rows_detail.json
```

Input rules (`batch/io_csv.py`, `api/routes/batch.py`):

- **Nothing is invented.** A missing required column, or a blank `record_id` / `unit_id`, is rejected with
  a 400 that names the file, line and column. Any other blank stays blank.
- **Separate columns per side.** In a single combined CSV, each side's IDs come only from its own
  `sold_*` / `returned_*` columns. A file without both sets of columns is rejected rather than compared
  with itself.
- **Missing or bad input fails open.** A missing photo, category or before-record, or a failed download
  or model call, gives an `uncertain` / `pending_review` row with a `failure_reason`, no grade and no
  confidence.

Output columns (`batch/io_csv.py` `OUTPUT_FIELDNAMES`):

- **`identity_match`** is carried forward from the before-file. `photo_identity_match` is the model's own
  verdict on the returned photos.
- **`agent_disposition`** is the engine's recommendation (empty when it made none).
- **`operator_disposition`** is that route only when `auto_approved=true`; otherwise it is
  `pending_review` until a person accepts or overrides it. Overrides accept only the four routes (422
  otherwise).
  - Auto-approve requires all of the following: an engine route, no review, no sign-off, no escalation,
    every check PASS at or above `RM_BATCH_AUTO_APPROVE_MIN_CONFIDENCE_BP` (default 8500 = 85%), and
    every sold-vs-returned ID present and equal. **The threshold is not yet calibrated** (no threshold
    sweep has been run).
  - A row needing sign-off can be finalized only by a caller with the sign-off permission who is not
    the job's uploader.
- **`sold_vs_returned_id_check`** is one of:
  - `matched`: all of `org_id`, `order_id`, `ordered_sku` and `ordered_asin` present on both records
    and equal;
  - `NOT MATCHED: …`;
  - `not checked: <field> missing (sold|returned)`.
- **`value_source`** is `csv_list_price` or `synthetic_default`. Without a CSV price the configured
  default is used and the UI shows "price assumed (synthetic)" next to any value-driven outcome (S02,
  R09, R10). Recovery rates and refurbish cost are always synthetic placeholders.

```sh
cd agent
uv run returns-manager batch process \
  --before  path/to/before.csv \
  --returned path/to/returned.csv \
  --out      path/to/output.csv \
  --max-requests 15
```

## 3. Disposition rules (generated from `disposition/engine.py`)

The engine is a pure function, `decide(inputs) -> DispositionDecision`. It runs in three steps:

1. Step 1 gates (first match wins).
2. Step 2 review flags. These never blank the route.
3. Step 3 route rules (first match wins).

Sign-off rules are then added on top of the route. A condition in the table shows only the `if` tests
around that return; each row also implies that no earlier row in the same step matched. The table is
produced by `python scripts/rule_table.py`, and `agent/tests/unit/test_docs.py` fails if this copy
drifts from the engine.

<!-- rule-table:start -->
| Rule | Step | Outcome | When (engine condition) | Reason recorded | engine.py line |
|---|---|---|---|---|---|
| R01b | 1 gate | no recommendation (review required) | `inp.inspection_state == 'skipped'` | `inp.skip_reason or 'no_product_reference'` | 292 |
| R01 | 1 gate | no recommendation (review required) | `inp.inspection_state != 'complete' or inp.usable_photo_count == 0` | `inspection_incomplete` | 294 |
| R02 | 1 gate | dispose + S01 sign-off if clearly empty; else provisional route (review required) | `inp.unit_presence != 'product_present'` | `item_not_present_or_unverified` | 296 |
| R03 | 1 gate | dispose + S01 sign-off (review required) | `inp.identity == 'no'` | `wrong_item_returned` | 298 |
| R03b | 1 gate | provisional route from the other evidence (review required) | `inp.identity == 'uncertain'` | `identity_unverified` | 300 |
| R05b | 1 gate | no recommendation (review required) | `gate is None and inp.cosmetic_grade is None and (not blockers & DECIDING_BLOCKERS)` | `condition_uncertain` | 307 |
| R03 | 1 gate | dispose + S01 sign-off (review required) | `gate is not None and gate[0] == 'R02' and (inp.identity == 'no') and (not _gate_routable(inp, 'R02'))` | `wrong_item_returned` | 325 |
| R00 | 2 flag | review flag (route unchanged) | `not inp.auto_disposition_enabled` | `review.append("assisted_mode")` | 264 |
| R04 | 2 flag | review flag (route unchanged) | `always` | `review += [f for f in REVIEW_FLAGS if f in inp.flags]` | 265 |
| R05 | 2 flag | review flag (route unchanged) | `provisional` | `review.append("essential_component_uncertain")` | 272 |
| R05c | 2 flag | review flag (route unchanged) | `inp.nonessential_uncertain` | `review.append("nonessential_component_uncertain")` | 284 |
| R05c | 2 flag | review flag (route unchanged) | `inp.blockers_undetermined` | `review.append("listing_blockers_undetermined")` | 286 |
| R06 | 3 route | restock | `inp.new_only and grade == 'new' and (not blockers) and (not inp.blockers_undetermined)` | `New-only category, factory-sealed and intact` | 182 |
| R99 | 3 route | no recommendation (review required) | `inp.new_only and policy_route in ('restock', 'refurbish')` | `f'policy {which}={policy_route} is not allowed for a New-only category'` | 186 |
| R07 | 3 route | liquidate if salvage > dispose_max_salvage, else dispose | `inp.new_only and policy_route == 'liquidate'` | `f'New-only category, not sealed-new; policy {which}=liquidate'` | 190 |
| R07 | 3 route | dispose | `inp.new_only` | `f'New-only category, not sealed-new; policy {which}=dispose'` | 191 |
| R08 | 3 route | dispose | `'consumable_used' in blockers` | `consumable item shows use` | 194 |
| R09 | 3 route | refurbish | `essential_missing and replaceable and gain >= inp.refurbish_min_net_gain_minor and base.route is not None and ROUTE_RANK[base.route] >= ROUTE_RANK['refurbish']` | `f'replaceable essential part(s) missing; net gain {gain}'` | 202 |
| R10 | 3 route | liquidate if salvage > dispose_max_salvage, else dispose | `essential_missing` | `essential part(s) missing and not refurbishable` | 205 |
| R10 | 3 route | liquidate if salvage > dispose_max_salvage, else dispose | `blockers & {'damaged_difficult_to_use', 'not_clean'}` | `damage or dirt makes the item unlistable as-is` | 208 |
| R11 | 3 route | refurbish | `'functional_test_required' in blockers and gain >= inp.refurbish_min_net_gain_minor` | `f'used electrical item needs a functional test; net gain {gain}'` | 213 |
| R11 | 3 route | liquidate | `'functional_test_required' in blockers` | `f'functional test needed but net gain {gain} too small'` | 216 |
| R12 | 3 route | restock | `grade == 'new' and (not blockers)` | `factory-sealed and intact` | 219 |
| R13 | 3 route | restock | `grade in inp.restock_used_grades and inp.completeness_status == 'complete'` | `f'used grade {grade} is restockable by policy{seal_note}'` | 228 |
| R13 | 3 route | restock | `grade in inp.restock_used_grades and inp.completeness_status == 'incomplete' and (not essential_missing) and (grade in GRADES_ALLOWING_NONESSENTIAL_MISSING)` | `f'{grade}: rubric allows non-essential material to be missing'` | 234 |
| R09b | 3 route | refurbish | `grade in inp.restock_used_grades and inp.completeness_status == 'incomplete' and (not essential_missing) and gain >= inp.refurbish_min_net_gain_minor` | `f'replaceable non-essential part(s) missing; net gain {gain}'` | 242 |
| R14 | 3 route | liquidate | `grade in inp.restock_used_grades and inp.completeness_status == 'incomplete' and (not essential_missing)` | `f'non-essential parts missing; not permitted at grade {grade}'` | 245 |
| R14 | 3 route | liquidate | `grade is not None and grade != 'new' and (grade not in inp.restock_used_grades)` | `f'used grade {grade} is outside restock_used_grades (business policy)'` | 250 |
| R99 | 3 route | no recommendation (review required) | `always (fallthrough)` | `rule_gap` | 254 |
| S03 | sign-off | route stands; human sign-off required | `gate is not None and gate[0] in ('R02', 'R03') and _gate_routable(inp, gate[0]) and inp.escalation_disagreement_resolved_by_reviewer` | `S03_escalation_disagreement_resolved` | 330 |
| S01 | sign-off | route stands; human sign-off required | `route == 'dispose'` | `S01_dispose_always` | 434 |
| S02 | sign-off | route stands; human sign-off required | `route not in (None, 'restock') and inp.list_price_minor >= inp.high_value_threshold_minor` | `S02_high_value` | 436 |
| S03 | sign-off | route stands; human sign-off required | `inp.escalation_disagreement_resolved_by_reviewer` | `S03_escalation_disagreement_resolved` | 438 |
<!-- rule-table:end -->

`high_value_threshold_minor` (S02) is `RM_HIGH_VALUE_THRESHOLD_MINOR`, default 500000 paise (₹5,000).
R09, R10 and S02 depend on the list price and on the recovery-rate placeholders.

## 4. Key design decisions and why

| Decision | Why |
|---|---|
| **The rules engine computes the disposition; the model never does.** | The model's output schema has no disposition field. The engine's decision is auditable and can be re-run against the same evidence without a model call (`inputs_sha256` pins the inputs). |
| **Rule 2: one Judgment session per inspection** (`RULES.md` §2 "Batch Your Model Calls", `decisions/ADR-002-rule-2-batch-inspection.md`). | All checks come back in one structured output, normally in one request, and at most `RM_MAX_ROUND_TRIPS` (default 2) requests including tool round trips. Escalation and audit are separate full re-judgments, never per-check calls. |
| **Fail open.** | Photos and the return record are stored before any model call. A model or provider failure leaves the return `pending` / `needs_attention` (or, in the batch tool, `uncertain` / `pending_review`) with a reason. A failure never produces a pass, a guessed grade or an auto-disposition. |
| **`uncertain` is a verdict, not a low-confidence pass.** | `judgment/fusion.py` `fuse_identity` confirms identity only with two matched critical product-body features or a barcode match. The consistency rules refuse to call a part missing unless the cited photo region shows where it would be. |
| **Tenancy is enforced by Postgres RLS, forced on every tenant table.** | Policy `org_id = NULLIF(current_setting('app.org_id', true), '')`, set per transaction (`db.tenant.transaction(org_id)`). The app connects as `rm_app_login` (NOSUPERUSER, NOBYPASSRLS) and refuses to boot if its role can bypass RLS. A user's org comes from `rm.user_memberships()` after JWT verification (the JWT carries no org), and an API key's org from `rm.resolve_api_key`. Cross-org access answers 404. |
| **Only real API keys authenticate.** | An `X-API-Key` is accepted only if it exists in `rm.api_keys`. The former `rmk_local_` / `rmk_demo_` prefix fallback was removed (`b73fcc1`). |
| **Gemini sessions are stateful** and chained with `previous_interaction_id`. A quota-exhausted primary model falls back to a fresh session on `RM_JUDGMENT_FALLBACK_MODEL`, never a continuation. | The daily free-tier quota guard (`llm/quota.py`) is never bypassed. Retrying into an exhausted budget would waste the remaining quota on one job. |
| **Evidence records are hash-chained per unit and superseded, never edited in place.** | Wording per `decisions/ADR-007`: "tamper-evident within the database (hash-chained)". Someone with direct write access to the database could rewrite the chain; `returns-manager` can append the ledger head to `anchors/ledger-anchors.jsonl` (`chain/anchor.py`) for an outside copy to compare against, but no anchors are committed yet. |
| **Audit is model re-judgment, off by default.** | With `RM_AUDIT_SAMPLE_RATE` > 0, a sampled unit is re-judged blind by `RM_AUDIT_MODEL`. The default rate is `0.0`. There is no human audit sampling. |

Other interfaces:

- **Webhooks** are signed with the `RM-Signature` header: `t=<unix>,v1=<hex HMAC-SHA256(secret, t + "." + raw_body)>` (`webhooks/signer.py`).
- **MCP:** `agent/src/returns_manager/mcp_server.py` uses the official `mcp` SDK (`MCPServer`) and exposes read-only evidence tools scoped to the caller's org.
- **Metrics:** JSON endpoints `GET /api/v1/metrics/summary` and `/economics`. There is no Prometheus exporter.

## 5. Configuration that the behaviour depends on

Defaults from `agent/src/returns_manager/config.py`; the repository-root `.env` can override them.

| Setting | Default |
|---|---|
| `RM_JUDGMENT_MODEL` | `gemini-3.8-flash` |
| `RM_JUDGMENT_FALLBACK_MODEL` | `gemini-3-flash-preview` |
| `RM_ESCALATION_MODEL` | `gemini-3.8-flash` |
| `RM_AUDIT_MODEL` | `gemini-3.6-flash` |
| `RM_EXPLAINER_MODEL` | `gemini-3.1-flash-lite` |
| `RM_AUDIT_SAMPLE_RATE` | `0.0` |
| `RM_MAX_ROUND_TRIPS` | `2` |
| `RM_HIGH_VALUE_THRESHOLD_MINOR` | `500000` (₹5,000) |
| `RM_BATCH_AUTO_APPROVE_MIN_CONFIDENCE_BP` | `8500`, not yet calibrated |

## 6. Status and known gaps

- **Tests.** `uv run returns-manager dev check` (from `agent/`) on 2026-09-29: 453 passed, 97 skipped; ruff, ruff format, mypy, reference validate and the boundary check all ok. The 97 skipped tests are the database (`db`) tests. They skip because no local Supabase
  was running, so **they have not been run**: tenancy/RLS, the job queue, the worker's retry and quota-hold logic
  and the load-test CLI are untested in this state.
- **Load test.** The only recorded run is `returns-manager load-test --mode replay --units 5 --concurrency 2`
  against the local database: 27.24 units/s, 0 duplicates, 0 drops, fail-open under an injected outage PASS
  (`build-log.md`). Live mode refuses without `--confirm-spend`. No larger run has been done.
- **Evaluation (C1).** There is no independently labelled sealed eval set (`eval/sealed/` and `eval/labels/`
  are empty), so there is no reported accuracy. `eval/runs/` holds a tooling check (`devmini-20260927`) and
  a single-labeller 30-unit self-labelled run (`manual-30row-self-labeled-20260927`; read its `NOTES.md`).
- **Contract examples (C2).** `agent/contract/examples/` holds 14 synthetic records (official scenarios S01-S10 plus an empty box, a box swap and an uncountable part). Each is produced by a real pipeline + rules-engine run (`agent/scripts/generate_example_contract_records.py`), and `test_t_con_20` fails if one drifts from what the engine computes. They are crafted judgments, not live model output.
- **Open findings** (`build-log.md`):
  - **F-018:** an over-length model field is caught only by local validation.
  - **F-019:** a battery/label misread was reduced but not eliminated.
  - **F-020:** the batch tool has no duplicate-photo check.
- **Findings files.** `findings/` holds F-001 and F-007…F-013; F-014…F-024 are only in the build log.
- **Inspection comparison panel.** Built, but not yet viewed against a real job (that needs live model calls).
- **A key in public history.** A committed `rmk_local_` key literal remains in the public git history
  (`8409211`). It no longer authenticates by its prefix. Whether it exists as a real row in `rm.api_keys`
  (and must be revoked) can only be checked with the database running.
