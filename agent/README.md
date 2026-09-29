# returns-manager (agent)

Evidence-backed returns inspection: identity, completeness and condition from a few phone photos, the
seller's own catalogue and Amazon's published condition guidelines. A deterministic rules engine then
computes one of four dispositions, `restock` / `refurbish` / `liquidate` / `dispose`, from the
inspection evidence. When it cannot recommend one, the recommendation is `null` with a reason, and the
row stays `pending_review` until a person decides. The model never decides the disposition.

See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for the data flow, the generated rule table and the
known gaps, and [`../ui/`](../ui/) for the operator console (React + Vite).

## Setup

```sh
cd agent
uv sync                      # Python 3.12, exact pins from uv.lock
```

Copy `.env.example` to `.env` (repo root). Fill in a Gemini API key (free tier,
[aistudio.google.com](https://aistudio.google.com) → Get API key). For the database-backed system, also
fill in the Supabase values that `npx supabase start` prints on first run. The model IDs are set per
role in `.env` (`RM_JUDGMENT_MODEL`, `RM_JUDGMENT_FALLBACK_MODEL`, `RM_ESCALATION_MODEL`,
`RM_AUDIT_MODEL`, `RM_EXPLAINER_MODEL`); see `src/returns_manager/config.py` for the defaults.

## Running the database-backed system

```sh
npx supabase start                  # Docker Desktop must be running; local Postgres + RLS
uv run returns-manager db migrate   # applies agent/migrations/0001…0011
uv run returns-manager seed demo    # two demo orgs, sample users, private storage buckets
uv run returns-manager dev check    # ruff + mypy + pytest (non-live) + reference validate + boundary check
uv run returns-manager worker       # process the job queue
uv run returns-manager api serve    # the HTTP API
```

### Connecting the UI (API key)

The API accepts only keys that exist in `rm.api_keys`; there is no built-in local or demo key. With the
database running and seeded, mint one for the UI:

```sh
uv run returns-manager keys create --org org_demo_alpha --scope admin --name ui-dev
```

The key is printed once. Paste it into the UI's Connect screen, or put it in `ui/.env` as
`VITE_API_KEY=<key>` to pre-fill that screen (`ui/.env` is git-ignored; never commit a key). The key's
`rmk_<env>_` prefix must match `RM_ENV`. `returns-manager keys revoke` retires a key. The scripts in
`../scratch/` read the key from `RM_API_KEY` and exit if it is unset.

| Command | What it does |
|---|---|
| `returns-manager dev check` | Lint, format check, types, non-live tests, reference validation, repository-boundary check. |
| `returns-manager batch process` | Standalone CSV + image-URL pipeline, no database (below). Makes real model calls. |
| `returns-manager eval run --dev-mini` | Runs the evaluation tooling on a small synthetic set. **Not an evaluation result.** |
| `returns-manager reference validate` | Validates every product card, rubric and policy file under `reference/`. |

## Running the standalone batch tool (no database)

```sh
uv run returns-manager batch process \
  --before  path/to/before.csv \
  --returned path/to/returned.csv \
  --out      path/to/output.csv \
  --default-category electronics \
  --max-requests 15
```

### Input files
- **Before-file columns:** `record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,identity_match,parts_list,time,photo_ref[,category][,list_price|,list_price_minor]`.
  - One row per unit at the time it was sold.
  - `identity_match` is carried forward unchanged.
  - `list_price` is rupees (e.g. `1299.50`) and `list_price_minor` is paise (e.g. `129950`). Both are optional.
- **Returned-file columns:** `record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,returned_photo_ref,time`.
  - One row per return, joined to its before-row on `unit_id`.
  - `returned_photo_ref` takes several URLs separated by `;`.
- **Single combined CSV** (API upload only): the layout of `manual_test_images/returns_input_30.csv`, with `sold_*` and `returned_*` columns.
- **Nothing is invented.**
  - A missing column, or a blank `record_id` / `unit_id`, is a 400 naming the file, line and column.
  - Other blanks stay blank.
  - Each side's IDs come only from that side's columns.

### Output columns
- The output holds every column of `data/returns_sample.csv` except `operator_id`, in the order set by `batch/io_csv.py` `OUTPUT_FIELDNAMES`, plus the columns below.
- **`photo_identity_match`**: the model's identity verdict on the returned photos.
- **`agent_disposition`**: the engine's recommendation.
- **`operator_disposition`**: that route only if **`auto_approved`** is `true`, otherwise `pending_review`.
  - Auto-approve needs an engine route with no review, no sign-off and no escalation.
  - Every check must PASS at a model-reported confidence ≥ `RM_BATCH_AUTO_APPROVE_MIN_CONFIDENCE_BP` (8500 by default, **not yet calibrated**).
  - Every sold-vs-returned ID must be present and equal.
- **`sold_vs_returned_id_check`**: `matched`, `NOT MATCHED: …` or `not checked: <field> missing (sold|returned)`. A mismatch is a review flag, not a disposition.
- **`failure_reason`**: why a row failed open (empty on a real model + engine result).
- **`value_source`**: `csv_list_price`, or `synthetic_default` when the before-file gave no price. The UI then shows "price assumed (synthetic)" next to S02, R09 and R10 outcomes.

### Parts and failures
- **Parts list:** the first part is the main, essential, non-replaceable part; every other listed part is essential and replaceable.
- **Fail open:** a bad image URL, a missing or unknown category, a model or provider failure, or the request budget running out leaves that row `uncertain` / `pending_review` with the reason. It never produces a guessed verdict and never drops the return record.

`manual_test_images/` holds a 30-row demonstration input (public, licensed Wikimedia Commons photos) and
the output of one live run.

## Testing

```sh
cd agent
uv run returns-manager dev check
```

This runs, in order:
1. `ruff check`
2. `ruff format --check`
3. `mypy`
4. `pytest` (non-live: no model spend; provider calls use scripted clients)
5. `reference validate`
6. the repository-boundary check

`dev check` exits non-zero if any step fails.

`uv run returns-manager dev check` (from `agent/`) on 2026-09-29: 453 passed, 97 skipped; ruff, ruff format, mypy, reference validate and the boundary check all ok.

The 97 skipped tests are marked `db`: tenancy/RLS, the job queue, the worker's retry and quota-hold logic,
and the load-test CLI. Without a running local Supabase they are skipped, not passed, and they were not run
for these numbers. Run `npx supabase start` and `dev check` again to exercise them.

## Evaluation

There is no independently labelled sealed eval set yet (`eval/sealed/` and `eval/labels/` are empty), so
there is no reported accuracy. `../eval/runs/` holds two runs:

- **`devmini-20260927`** is a tooling check on a small synthetic set. It is not a result.
- **`manual-30row-self-labeled-20260927`** is 30 units with live model calls, labelled by one person who
  also designed the set. **Read its `NOTES.md` before `report.md`**: it lists where this falls short of the
  required eval (one labeller, not two independent ones; 30 units, not ≥ 50; ground truth not blind).

## What is still open

- A real sealed evaluation (C1).
- The other 13 contract examples (C2; 1 of 14 exists).
- Running the `db` tests against a live database.
- **Open findings:**
  - **F-018:** an over-length model field is caught only by local validation.
  - **F-019:** a battery/label misread was reduced but not eliminated.
  - **F-020:** the batch tool has no duplicate-photo check.
- **The committed key.** The `rmk_local_` key literal committed in `8409211` is still in public history. It no longer
  authenticates by its prefix. Whether it exists in `rm.api_keys` (and must be revoked) needs the
  database running.
