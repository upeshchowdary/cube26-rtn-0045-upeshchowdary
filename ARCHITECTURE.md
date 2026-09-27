# Architecture — Returns Manager (Cube Buildathon 04)

This document describes what is actually implemented in this repository: the data flow, the
service boundaries, the key design decisions and why they were made, and the trade-offs that
were consciously accepted rather than silently skipped. Where a claim needs evidence, it
points at the code or at `build-log.md`/`decisions/` rather than asserting it.

## 1. What the agent does

From 2–3 phone photos of a returned product plus the seller's own catalogue, order record,
parts list and Amazon's published condition guidelines, the agent answers four questions and
records the evidence behind each answer:

```
Returned item
     │
     ▼
1. Identity      — is this the SKU/ASIN that was ordered?
     │
     ▼
2. Completeness  — are the expected parts present?
     │
     ▼
3. Condition     — what grade, against the published condition scale?
     │
     ▼
4. Disposition   — restock / refurbish / liquidate / dispose / pending_review
     │
     ▼
Evidence record (identity + completeness + condition + disposition, traceable)
```

The disposition is **never** decided by the model. A deterministic rules engine
(`disposition/engine.py`) computes it from the model's structured judgment output plus the
seller's category policy and condition rubric. The model's job is limited to reporting what it
observed (identity match, per-part visibility, condition indicators); the model's own output
schema has no disposition field at all.

## 2. Two ways to run it

### 2.1 The full, database-backed system

This is the "real" system: a FastAPI HTTP API, a durable job queue, and a Postgres database
(local Supabase) with tenancy enforced by Row-Level Security.

```
                         ┌─────────────────────────────────────────────┐
                         │              FastAPI (api/app.py)            │
                         │  /health  /ready                             │
                         │  security · intake · jobs · simulate ·       │
                         │  review · chain · evidence · explainer ·     │
                         │  webhooks · metrics  (routers, §15)          │
                         └───────────────────┬───────────────────────────┘
                                              │ HTTP
                                              ▼
   ┌───────────┐    photos + return record    ┌─────────────────┐
   │  Seller /  │ ─────────────────────────────▶│  intake (§9.1)  │
   │  operator  │                               │  images.py:     │
   └───────────┘                               │  sniff, decode,  │
                                                 │  preprocess      │
                                                 └────────┬─────────┘
                                                          │ stored (photos before any model call)
                                                          ▼
                                            ┌─────────────────────────┐
                                            │  rm.* tables (Postgres)  │
                                            │  RLS FORCED per org_id   │
                                            └────────────┬─────────────┘
                                                          │ enqueued job
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  jobs/worker.py             │
                                          │  kill switch → circuit      │
                                          │  breaker → daily quota →    │
                                          │  handler (§10)              │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  inspection/service.py      │
                                          │  JudgmentHandler             │
                                          │  assembles the context       │
                                          │  bundle, calls llm/loop.py    │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  Gemini Interactions API     │
                                          │  (llm/gemini_client.py)      │
                                          │  one stateful session,       │
                                          │  chained via                 │
                                          │  previous_interaction_id     │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  judgment/*.py               │
                                          │  fuse_identity, consistency  │
                                          │  rules (C01/C02), claims     │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  disposition/engine.py       │
                                          │  deterministic R01…R14/R99   │
                                          └──────────────┬───────────────┘
                                                          ▼
                                          ┌────────────────────────────┐
                                          │  contract/*.py                │
                                          │  evidence record (flat view,  │
                                          │  hash-chained per unit)       │
                                          └────────────────────────────┘
```

Run it with:

```sh
cd agent
uv sync
npx supabase start          # Docker Desktop must be running
uv run returns-manager db migrate
uv run returns-manager seed demo
uv run returns-manager dev check     # ruff + mypy + pytest + reference validate + boundary check
uv run returns-manager worker        # start processing the job queue
uv run returns-manager api serve     # start the HTTP API
```

### 2.2 The standalone batch tool (no database)

`batch/` is a second, independent entry point built to exercise the real judgment pipeline
and the real deterministic disposition engine **without** Supabase/Postgres: a CSV-in,
CSV-out tool that still makes real Gemini calls and runs the real rules engine, just without
persistence, RLS, the job queue, or the API layer.

```
before.csv  (sold record: org_id, order_id, sku, asin, identity_match, parts_list, photo_ref)
returned.csv (returned record: org_id, order_id, sku, asin, returned_photo_ref)
     │                                  │
     └──────────────┬───────────────────┘
                     │ joined on unit_id
                     ▼
        batch/runner.py: process_returned_row()
                     │
      ┌──────────────┼───────────────────────────────┐
      ▼              ▼                                ▼
 fetch photos    build a synthetic product   compare sold-vs-returned
 (images.py)     card (cards.py) from        IDs (check_id_match) —
                 parts_list                  independent of the photo
      │              │                                │
      └──────────────┴────────────────┬───────────────┘
                                       ▼
                        llm/loop.run_session (same code
                        path as the DB-backed system)
                                       ▼
                        disposition/engine.run_pipeline
                        (same deterministic rules)
                                       ▼
                        output.csv: identity_match, parts_missing,
                        observed_state, amazon_condition,
                        operator_disposition, sold_vs_returned_id_check
```

`operator_disposition` is the engine's real computed route whenever it has one, overridden to
`wrong_product` when the sold-vs-returned ID check disagrees (mismatched order/SKU paperwork
on the returned label outranks a correct-looking photo), and falls back to `pending_review`
only when the engine genuinely could not compute a route.

Run it with:

```sh
cd agent
uv run returns-manager batch process \
  --before  manual_test_images/before.csv \
  --returned manual_test_images/returned.csv \
  --out      manual_test_images/output.csv
```

## 3. Key design decisions and why

| Decision | Why |
|---|---|
| **Disposition is computed by a deterministic rules engine, never by the model.** | The model's structured output has no disposition field. `disposition/engine.py` gates on identity/completeness/condition resolution (rules R01–R05b: no recommendation possible) then routes to restock/refurbish/liquidate/dispose (R06–R14, R99 = rule gap). This makes the disposition auditable and re-runnable against the same evidence without a model call. |
| **Fail open, always.** | Photos and the return record are persisted *before* any model call. A model/provider failure never discards the case — it leaves the return `pending`/`uncertain` with a reason attached (`jobs/retry.py: classify_error`, `_PROVIDER_CLASSES`). Found and fixed three real fail-open gaps in the batch tool this way: a single bad photo URL discarding every other photo for the same return, no RPM throttling causing avoidable bursts of 429s, and a disposition-mapping bug that collapsed every non-restock outcome to `pending_review` even when the engine had computed a specific route (`build-log.md` F-016, F-017, F-022). |
| **`uncertain` is a first-class verdict, not a low-confidence pass.** | `judgment/fusion.py`'s `fuse_identity` requires two independently-matched critical product-body features (`body_matches >= 2`) or a barcode match before confirming identity as `yes` — one match alone always downgrades to `uncertain`. Consistency rules C01/C02 (`judgment/consistency.py`) similarly refuse to confirm a part "missing" unless the model tagged the cited photo region as showing the accessory/interior area. |
| **Tenancy is enforced by Postgres RLS, forced on every tenant table, not by application-layer filtering.** | Policy `org_id = NULLIF(current_setting('app.org_id', true), '')`, tenant set per transaction (`db.tenant.transaction(org_id)`). The app connects as `rm_app_login` (`NOSUPERUSER`, `NOBYPASSRLS`) and refuses to boot if that role can bypass RLS. Cross-org access answers 404, not 403 (existence itself is not leaked). |
| **One Gemini session per inspection, stateful, chained via `previous_interaction_id`.** | At most `RM_MAX_ROUND_TRIPS` (default 2) requests per session including tool round trips — verified directly against the installed `google-genai==2.25.0` source rather than assumed (`build-log.md`'s P5 spike), because the SDK's own interactions API has fields and behavior (e.g. function results can carry images; `tool_choice` needs the `{"allowed_tools": {"mode": "auto"}}` shape) that aren't guessable from the brief alone. |
| **The daily Gemini free-tier quota guard is never bypassed**, and a quota-exhausted primary model falls back to a fresh session on a different model (`RM_JUDGMENT_FALLBACK_MODEL`), never a continuation of the failed session. | Free-tier daily budgets are small (tested empirically against real limits this session); silently retrying into the same exhausted budget wastes the whole day's remaining capacity on one stuck job. |
| **Evidence records are hash-chained per unit, not claimed as immutable.** | Per `RULES.md`'s honesty rules and `decisions/ADR-007`, the system says "tamper-evident within the database (hash-chained), not immutable" — the stronger claim was deliberately avoided because it isn't what was built. |

## 4. Known limitations (said plainly, not hidden)

- **F-018** (`build-log.md`): the Gemini-facing JSON schema strips `maxLength` (not a keyword Gemini
  supports), so an over-length free-text field from the model is only caught after the fact by local
  Pydantic validation, as a retryable `schema_error`. Not eliminated, only caught.
- **F-019**: a specific battery/label misread (the model reading a phone's fixed FCC label as the
  battery's own body) was reduced but not reliably eliminated by a prompt fix — confirmed as a
  measured *recurrence*, not a one-time bug, on an independent re-run of the same photo.
- **F-020**: the standalone batch tool has no equivalent of a perceptual-hash duplicate-photo check;
  the real DB-backed pipeline has `PhotoGate.integrity_flags` for this, the batch tool does not.
- **No formal, independently-labeled evaluation set exists yet** (`eval/sealed/`, `eval/labels/` are
  both empty). `eval run` refuses to fabricate one — it errors out rather than running against
  nonexistent sealed data, and only accepts `--dev-mini` (a small, explicitly-synthetic set) for
  proving the eval *pipeline* works. See the evaluation report for what was measured instead, and
  what a real eval still needs.
