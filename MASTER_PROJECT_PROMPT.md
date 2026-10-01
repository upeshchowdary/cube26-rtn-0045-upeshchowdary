# Returns Manager (Cube Buildathon 04, track RTN-0045): project dossier

**Author:** Upesh Chowdary
**Branch:** `upeshchowdary`
**Revised:** 2026-09-29, after the audit fix passes (Stage 1: `b73fcc1`…`d4344fd`; Stage 2: `06c5c85` onward). Every claim below was checked against the code at that point.
**Tests:** `uv run returns-manager dev check` (from `agent/`) on 2026-09-29: 453 passed, 97 skipped; ruff, ruff format, mypy, reference validate and the boundary check all ok. The 97 skipped tests are the database tests; they were **not run** (no local Supabase).

## Phase 6 status snapshot (2026-09-30)

Documentation is now aligned to the current repo state.

- Validation: `cd agent && uv run returns-manager dev check` exited 0 on 2026-09-30. The current unit regression run also shows `pytest tests/unit -q` → `558 passed` in `89.13s`.
- Smoke run, not an eval: `agent/.data/batch_jobs/org_demo_alpha/.../meta.json` recorded `total_rows=4`, `uncertain=4`, `live_requests=2`; notes include `quota_exhausted` and `no_return_photo`. This is a smoke check for wiring, not a measured evaluation result.
- Honest open items remain: no real C1 eval set, no threshold calibration, no Recovery-pod contract agreement, and no measured 3D performance benchmark for the redesign. The redesign remains UI mockup / 2.5D composition work unless a measured benchmark is captured.

---

## 1. What it is

Returns Manager turns a returned package into a documented decision. From 2-3 phone photos of the
returned item, the seller's catalogue and parts list, the order record and Amazon's published condition
guidelines, it records four things:

1. **Identity:** yes / no / uncertain.
2. **Completeness:** each part present / missing / uncertain.
3. **Condition:** one of the five Amazon grades (New, Used - Like New, Used - Very Good, Used - Good,
   Used - Acceptable), or uncertain.
4. **Disposition:** one of four (restock, refurbish, liquidate, dispose), or no recommendation, with the
   reason, held for review.

The model (Gemini, via the Interactions API) reports what it observed in one structured output. The
rules engine (`agent/src/returns_manager/disposition/engine.py`) computes the disposition from that
evidence. The model's output has no disposition field.

Configured model IDs (defaults in `agent/src/returns_manager/config.py`; the root `.env` can override
them per role):

| Role | Setting | Default |
|---|---|---|
| Judgment | `RM_JUDGMENT_MODEL` | `gemini-3.8-flash` |
| Judgment fallback (quota exhausted) | `RM_JUDGMENT_FALLBACK_MODEL` | `gemini-3-flash-preview` |
| Escalation | `RM_ESCALATION_MODEL` | `gemini-3.8-flash` |
| Audit re-judgment | `RM_AUDIT_MODEL` | `gemini-3.6-flash` |
| Explainer | `RM_EXPLAINER_MODEL` | `gemini-3.1-flash-lite` |

## 2. Principles the code enforces

1. **Tenancy.**
   - Postgres row-level security is enabled and forced on every tenant table.
   - Policy: `org_id = NULLIF(current_setting('app.org_id', true), '')`, set per transaction.
   - The app role (`rm_app_login`) cannot bypass RLS, and the app refuses to boot if it could.
   - A user's org comes from `rm.user_memberships()` after JWT verification; the JWT carries no org.
   - An API key's org comes from `rm.resolve_api_key`, and only keys in `rm.api_keys` authenticate.
   - Cross-org access answers 404.
2. **Engineering Rule 2, "Batch your model calls"** (`RULES.md` §2, `decisions/ADR-002`).
   - One Judgment session per inspection carries every check in one structured output.
   - It is normally one request, and at most `RM_MAX_ROUND_TRIPS` (default 2) including tool round trips.
   - Escalation and audit are separate full re-judgments, never per-check calls.
3. **Perception and policy are separate.** The model reports observations; the rules engine decides the
   route. This is a design principle of the project, not Rule 2.
4. **Fail open.**
   - Photos and the return record are stored before any model call.
   - A model or provider failure leaves the return pending / needs attention (batch tool: `uncertain` /
     `pending_review`) with a reason.
   - It never produces a pass, a guessed grade or an auto-disposition.
5. **Tamper-evident within the database (hash-chained)** (`decisions/ADR-007`).
   - Every event is appended to a per-unit chain: RFC 8785 canonical JSON, SHA-256.
   - A correction mints a new record version that supersedes the old one, which is kept.
   - Someone with direct database write access could still rewrite the chain. Anchoring the ledger head
     outside the database (`chain/anchor.py`) is what would expose that, and no anchors are committed yet.

## 3. Build history (phases P0-P14 and the batch/UI work)

Details, failures and evidence per phase are in `build-log.md`.

- **P0, hygiene.**
  - Pre-commit config with gitleaks, ruff and a 5 MB file cap (`.pre-commit-config.yaml`).
  - `scripts/check_boundary.py`: branch name, organiser-owned files, forbidden files, size cap.
  - The hooks must be installed per clone (`agent/.venv/Scripts/pre-commit install`, with gitleaks on
    PATH). They were not installed in the clone used for the audit fixes.
- **P1, tenancy and storage.**
  - Migrations in `agent/migrations/` (11 files, `0001_roles_and_schema.sql` … `0011_webhook_persistence.sql`).
  - Tables include `rm.organizations`, `rm.memberships`, `rm.returns`, `rm.return_photos`, `rm.orders` and `rm.products`.
  - Dependencies are locked with hashes in `agent/uv.lock`. Two specs in `pyproject.toml` are still `>=` (`mcp`, `scikit-learn`).
- **P2, reference data.**
  - Condition rubrics per category under `reference/rubrics/amazon.co.uk/`, with exactly the five Amazon grades.
  - Amazon's "unacceptable condition" text is kept under `unacceptable_conditions`, not as grades.
  - Category policies under `reference/policies/`.
- **P3, intake.**
  - Magic-byte sniffing (JPEG, PNG, WebP, HEIC/HEIF) and a 60M-pixel decode cap.
  - The stored EXIF summary excludes GPS.
  - Downscaling to a 1568 px long edge (`RM_ANALYSIS_LONG_EDGE`).
  - Quality gate: sharpness and exposure, `intake/quality.py`.
  - Perceptual hash for duplicate photos.
  - Barcode reading with `zxing-cpp`.
- **P4, jobs.**
  - Database-backed job queue with leases, a circuit breaker, a per-model rate limiter, and a daily request quota on the Pacific day.
  - Provider failures fail open.
- **P5-P7, judgment, engine, chain.**
  - Gemini Interactions client with stateful sessions (`previous_interaction_id`) and structured output (`llm/schemas.py`).
  - Identity fusion and consistency rules (`judgment/`).
  - The rules engine (section 4).
  - The per-unit hash chain (`0008_event_chain.sql`, `chain/`).
- **P8-P9, human loop.**
  - Review queue, overrides and sign-off rules (S01-S03, section 4).
  - Blind model re-judgment for escalation and audit.
  - Audit sampling is `RM_AUDIT_SAMPLE_RATE`, default **0.0** (off). It is model re-judgment, not human sampling.
- **P10, contracts.**
  - OpenAPI for the HTTP API.
  - Evidence-record JSON schema and flat view (`agent/contract/`).
  - MCP server at `agent/src/returns_manager/mcp_server.py` on the official `mcp` SDK (`MCPServer`, formerly FastMCP), with read-only evidence tools scoped to the caller's org.
- **P11, observability.**
  - JSON metrics at `GET /api/v1/metrics/summary` and `/economics`; each figure states its method and `n`.
  - Structured logs (structlog). There is no Prometheus exporter.
  - Spend guards: bulk live work refuses without an explicit flag.
- **P12, evaluation tooling.**
  - Agreement, Cohen's kappa, selective prediction, confusion matrices, sealed run manifests (`eval/`).
  - No sealed, independently labelled set exists yet (section 6).
- **P13, load.** The one recorded run, from `build-log.md`:
  - `returns-manager load-test --mode replay --units 5 --concurrency 2` against the local database;
  - 27.24 units/s, 0 duplicates, 0 drops, fail-open under an injected outage PASS;
  - live mode refuses without `--confirm-spend`.
  - No larger run has been done.
- **P14, extensions.**
  - Webhooks signed with the `RM-Signature` header (`t=<unix>,v1=<hex HMAC-SHA256(secret, t + "." + raw_body)>`, `webhooks/signer.py`).
  - Explainer agent whose answers must cite evidence the record contains.
  - ADR-000…ADR-010 in `decisions/`.
- **Batch tool and UI.**
  - `batch/` runs the same session and engine on a CSV of image URLs without the database.
  - `ui/` is a React + Vite + TypeScript operator console.
  - The batch tool's input rules, auto-approve flag and output columns are in `ARCHITECTURE.md` §2.2.

## 4. Disposition rules (generated from `disposition/engine.py`)

The engine runs in three steps, each first-match-wins in the order listed:

1. Step 1 gates.
2. Step 2 review flags. These never change the route.
3. Step 3 route rules.

Sign-off rules are added on top of the route. The table is produced by `python scripts/rule_table.py`;
`agent/tests/unit/test_docs.py` fails if this copy drifts from the engine.

<!-- rule-table:start -->
| Rule | Step | Outcome | When (engine condition) | Reason recorded | engine.py line |
|---|---|---|---|---|---|
| R01b | 1 gate | no recommendation (review required) | `inp.inspection_state == 'skipped'` | `inp.skip_reason or 'no_product_reference'` | 270 |
| R01 | 1 gate | no recommendation (review required) | `inp.inspection_state != 'complete' or inp.usable_photo_count == 0` | `inspection_incomplete` | 272 |
| R02 | 1 gate | no recommendation (review required) | `inp.unit_presence != 'product_present'` | `item_not_present_or_unverified` | 274 |
| R03 | 1 gate | no recommendation (review required) | `inp.identity == 'no'` | `wrong_item_returned` | 276 |
| R03b | 1 gate | no recommendation (review required) | `inp.identity == 'uncertain'` | `identity_unverified` | 278 |
| R05b | 1 gate | no recommendation (review required) | `gate is None and inp.cosmetic_grade is None and (not blockers & DECIDING_BLOCKERS)` | `condition_uncertain` | 285 |
| R00 | 2 flag | review flag (route unchanged) | `not inp.auto_disposition_enabled` | `review.append("assisted_mode")` | 253 |
| R04 | 2 flag | review flag (route unchanged) | `always` | `review += [f for f in REVIEW_FLAGS if f in inp.flags]` | 254 |
| R05 | 2 flag | review flag (route unchanged) | `provisional` | `review.append("essential_component_uncertain")` | 256 |
| R05c | 2 flag | review flag (route unchanged) | `inp.nonessential_uncertain` | `review.append("nonessential_component_uncertain")` | 262 |
| R05c | 2 flag | review flag (route unchanged) | `inp.blockers_undetermined` | `review.append("listing_blockers_undetermined")` | 264 |
| R06 | 3 route | restock | `inp.new_only and grade == 'new' and (not blockers) and (not inp.blockers_undetermined)` | `New-only category, factory-sealed and intact` | 183 |
| R99 | 3 route | no recommendation (review required) | `inp.new_only and policy_route in ('restock', 'refurbish')` | `f'policy {which}={policy_route} is not allowed for a New-only category'` | 187 |
| R07 | 3 route | liquidate if salvage > dispose_max_salvage, else dispose | `inp.new_only and policy_route == 'liquidate'` | `f'New-only category, not sealed-new; policy {which}=liquidate'` | 191 |
| R07 | 3 route | dispose | `inp.new_only` | `f'New-only category, not sealed-new; policy {which}=dispose'` | 192 |
| R08 | 3 route | dispose | `'consumable_used' in blockers` | `consumable item shows use` | 195 |
| R09 | 3 route | refurbish | `essential_missing and replaceable and gain >= inp.refurbish_min_net_gain_minor and base.route is not None and ROUTE_RANK[base.route] >= ROUTE_RANK['refurbish']` | `f'replaceable essential part(s) missing; net gain {gain}'` | 203 |
| R10 | 3 route | liquidate if salvage > dispose_max_salvage, else dispose | `essential_missing` | `essential part(s) missing and not refurbishable` | 206 |
| R10 | 3 route | liquidate if salvage > dispose_max_salvage, else dispose | `blockers & {'damaged_difficult_to_use', 'not_clean'}` | `damage or dirt makes the item unlistable as-is` | 209 |
| R11 | 3 route | refurbish | `'functional_test_required' in blockers and gain >= inp.refurbish_min_net_gain_minor` | `f'used electrical item needs a functional test; net gain {gain}'` | 214 |
| R11 | 3 route | liquidate | `'functional_test_required' in blockers` | `f'functional test needed but net gain {gain} too small'` | 217 |
| R12 | 3 route | restock | `grade == 'new' and (not blockers)` | `factory-sealed and intact` | 220 |
| R13 | 3 route | restock | `grade in inp.restock_used_grades and inp.completeness_status == 'complete'` | `f'used grade {grade} is restockable by policy'` | 224 |
| R13 | 3 route | restock | `grade in inp.restock_used_grades and inp.completeness_status == 'incomplete' and (not essential_missing) and (grade in GRADES_ALLOWING_NONESSENTIAL_MISSING)` | `f'{grade}: rubric allows non-essential material to be missing'` | 230 |
| R14 | 3 route | liquidate | `grade in inp.restock_used_grades and inp.completeness_status == 'incomplete' and (not essential_missing)` | `f'non-essential parts missing; not permitted at grade {grade}'` | 234 |
| R14 | 3 route | liquidate | `grade is not None and grade != 'new' and (grade not in inp.restock_used_grades)` | `f'used grade {grade} is outside restock_used_grades (business policy)'` | 239 |
| R99 | 3 route | no recommendation (review required) | `always (fallthrough)` | `rule_gap` | 243 |
| S01 | sign-off | route stands; human sign-off required | `r.route == 'dispose'` | `S01_dispose_always` | 314 |
| S02 | sign-off | route stands; human sign-off required | `r.route not in (None, 'restock') and inp.list_price_minor >= inp.high_value_threshold_minor` | `S02_high_value` | 316 |
| S03 | sign-off | route stands; human sign-off required | `inp.escalation_disagreement_resolved_by_reviewer` | `S03_escalation_disagreement_resolved` | 318 |
<!-- rule-table:end -->

S02's threshold is `RM_HIGH_VALUE_THRESHOLD_MINOR`, default 500000 paise (₹5,000). In the batch tool, a
row without a CSV list price uses a configured default price. It is marked
`value_source=synthetic_default`, and the UI shows "price assumed (synthetic)" next to any S02, R09 or
R10 outcome.

**Batch auto-approve** (`batch/auto_approve.py`) is a flag, not an override. It lets the engine's own
route stand only when all of these hold:

- no review, sign-off or escalation;
- every check PASS at a model-reported confidence ≥ `RM_BATCH_AUTO_APPROVE_MIN_CONFIDENCE_BP` (8500);
- every sold-vs-returned ID present and equal.

**The threshold is not yet calibrated**: no threshold sweep has been run.

## 5. Problems found and how they were fixed

| # | Problem | Fix |
|---|---|---|
| 1 | The Gemini SDK retried 429s silently and burned daily quota (F-011). | SDK retries disabled, so 429s reach the app's own quota guard. |
| 2 | A `tool_choice` shape accepted by the SDK's stubs was rejected by the live API (F-023). | Fixed to the shape the live API accepts; logged as a reminder that a live call is the real test. |
| 3 | Git for Windows crashed intermittently (0xC0000005) during checks. | `scripts/check_boundary.py` and `cli/dev.py` retry on those exit codes. |
| 4 | The chain-verification route took `org_id` from a query parameter and had no authentication. | The route now uses the authenticated principal's org and requires `Permission.EVIDENCE_READ` (`c792362`). |
| 5 | Any `rmk_local_`/`rmk_demo_` string was accepted as an admin API key. | Removed; only keys in `rm.api_keys` authenticate (`b73fcc1`). A gitleaks rule now catches `rmk_` keys. |
| 6 | The batch tool replayed a stored answer key and guessed verdicts from filenames when the model call failed. | Such rows now fail open with a `failure_reason` and no confidence (`9fa5d4d`). |
| 7 | The batch layer and UI used a fifth disposition value for wrong items. | Four dispositions only; a wrong item is R03 plus a review flag (`96be452`). |
| 8 | A UI heuristic overrode the engine's route and skipped required sign-offs. | Auto-approve is a backend flag on engine-settled rows only; sign-off needs the permission and a second person (`b29c256`). |
| 9 | The CSV importer invented IDs, SKUs and timestamps for blank fields, and an ID check could "match" on them. | Blank required fields are a 400; a blank ID is "not checked", never "matched" (`06c5c85`). |

## 6. Not done yet

- **Evaluation (C1):** no sealed, independently labelled eval set, so no reported accuracy.
  `eval/runs/manual-30row-self-labeled-20260927` is a single-labeller 30-unit run; read its `NOTES.md`.
- **Contract examples (C2):** 1 of the 14 required examples exists (`agent/contract/examples/`).
- **Database tests:** the `db` tests have not been run for the current numbers (no local Supabase).
- **Open findings:**
  - **F-018:** an over-length model field is caught only by local validation.
  - **F-019:** a battery/label misread was reduced but not eliminated.
  - **F-020:** the batch tool has no duplicate-photo check.
- **Findings files:** `findings/` holds F-001 and F-007…F-013; F-014…F-024 are only in `build-log.md`.
- **Committed key:** a `rmk_local_` key literal committed in `8409211` remains in public history. It no
  longer authenticates by prefix. Whether it exists in `rm.api_keys` needs the database.
- **No demo video is committed.**

## 7. Prompt for a new coding agent on this repository

```markdown
You are working on Returns Manager (Cube Buildathon 04, track RTN-0045). Read CLAUDE.md first.

1. The rules engine (agent/src/returns_manager/disposition/engine.py) computes the disposition from the
   inspection evidence. The model reports observations only; its output has no disposition field.
   Dispositions are restock, refurbish, liquidate, dispose; otherwise no recommendation plus a reason,
   held for review. Grades are the five Amazon grades. Do not add values to either.
2. Tenancy: RLS forced on every rm.* tenant table; open transactions only via db.tenant.transaction(org_id).
3. Rule 2: one Judgment session per inspection, all checks in one structured output, at most
   RM_MAX_ROUND_TRIPS requests.
4. Fail open: a model or provider failure leaves the return pending with a reason. Never guess a grade,
   never invent input data, never replay stored answers.
5. Wording: "tamper-evident within the database (hash-chained)"; follow the forbidden-language table in
   CLAUDE.md.
6. Run `uv run returns-manager dev check` (from agent/) before committing. State test counts with the date
   and command, and say how many database tests were skipped.
```

## 8. Repository layout

```
cube26-rtn-0045-upeshchowdary/
├── agent/
│   ├── src/returns_manager/
│   │   ├── api/            FastAPI app and routers
│   │   ├── batch/          standalone CSV + image-URL pipeline, auto-approve flag
│   │   ├── chain/          canonical JSON, per-unit hash chain, ledger anchor
│   │   ├── disposition/    the rules engine
│   │   ├── explainer/      grounded explainer agent
│   │   ├── intake/         image sniffing, quality gate, barcodes
│   │   ├── jobs/           job queue, worker, retry, rate limiting
│   │   ├── judgment/       identity fusion, consistency rules, pipeline
│   │   ├── llm/            Gemini client, session loop, output schemas, quota guard
│   │   ├── review/         review queue, overrides, sign-off
│   │   ├── webhooks/       delivery and RM-Signature signing
│   │   └── mcp_server.py   MCP server (official mcp SDK)
│   ├── migrations/         0001…0011
│   ├── contract/           evidence-record schema, flat view, examples, MCP tool docs
│   └── tests/              unit tests (db-marked tests need local Supabase)
├── ui/                     React + Vite operator console
├── decisions/              ADR-000…ADR-010
├── findings/               F-001, F-007…F-013
├── reference/              rubrics, policies, product cards
├── eval/                   eval runs (sealed/ and labels/ are empty)
├── scripts/                check_boundary.py, rule_table.py
├── scratch/                ad hoc scripts (read the API key from RM_API_KEY)
├── ARCHITECTURE.md
├── MASTER_PROJECT_PROMPT.md
└── build-log.md
```
