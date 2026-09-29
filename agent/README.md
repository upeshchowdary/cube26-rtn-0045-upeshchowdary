# returns-manager (agent)

Evidence-backed returns inspection: identity, completeness, condition and disposition from a
few phone photos, the seller's own catalogue and Amazon's published condition guidelines. The
disposition (`restock` / `refurbish` / `liquidate` / `dispose` / `pending_review`) is always
computed by a deterministic rules engine from the model's structured observations — the model
itself never decides it. See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for the full data flow
and design decisions, and [`../frontend/`](../frontend/) for the operator console UI (static
site, real evidence data from this pipeline, not yet wired to the live API).

## Setup

```sh
cd agent
uv sync                      # Python 3.12, exact pins from uv.lock
```

Copy `.env.example` to `.env` (repo root) and fill in a Gemini API key (free tier,
[aistudio.google.com](https://aistudio.google.com) → Get API key) plus, if you want the
database-backed system, the Supabase values `npx supabase start` prints on first run.

## Running the full, database-backed system

```sh
npx supabase start                  # Docker Desktop must be running; local Postgres + RLS
uv run returns-manager db migrate
uv run returns-manager seed demo    # two demo orgs, sample users, private storage buckets
uv run returns-manager dev check    # ruff + mypy + pytest + reference validate + boundary check
uv run returns-manager worker       # start processing the job queue
uv run returns-manager api serve    # start the HTTP API (/health, /ready, and the routers
                                     # under intake/jobs/review/chain/evidence/explainer/
                                     # webhooks/metrics)
```

`returns-manager --help` lists every command group. The ones most relevant to reviewing this
submission:

| Command | What it does |
|---|---|
| `returns-manager dev check` | The full local quality gate: lint, types, tests, reference validation, repo-boundary check. |
| `returns-manager batch process` | Standalone CSV+image-URL pipeline, no database — see below. |
| `returns-manager eval run --dev-mini` | Exercises the evaluation pipeline end to end on a small, explicitly-synthetic set. **Not a real evaluation** — see `eval/README.md` (once written) or the evaluation report for what a real one needs. |
| `returns-manager reference validate` | Validates every product card, rubric and policy file under `reference/`. |

## Running the standalone batch tool (no database)

Built specifically so the real judgment pipeline and the real deterministic disposition
engine can be exercised and tested without Docker/Supabase — a plain CSV in, CSV out:

```sh
uv run returns-manager batch process \
  --before  manual_test_images/before.csv \
  --returned manual_test_images/returned.csv \
  --out      manual_test_images/output.csv \
  --default-category electronics \
  --max-requests 30
```

- **Before-file columns**: `record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,identity_match,parts_list,time,photo_ref[,category]`
  — one row per unit at the time it was sold. `identity_match` here is carried forward into
  the output unchanged, never re-derived by the agent.
- **Returned-file columns**: `record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,returned_photo_ref,time`
  — one row per return, joined to its before-row on `unit_id`. `returned_photo_ref` accepts
  multiple photo URLs separated by `;`.
- **Output columns** match `data/returns_sample.csv`'s shape (minus `operator_id`) plus one
  addition: `sold_vs_returned_id_check` — a plain data comparison of `org_id`/`order_id`/
  `ordered_sku`/`ordered_asin` between the two records, independent of anything a photo
  shows. A mismatch here forces `operator_disposition` to `wrong_product`, overriding
  whatever the photo-based pipeline or fail-open path would otherwise have said (mismatched
  paperwork on a returned package outranks a correct-looking photo) — except when there's no
  sold record at all to compare against, which stays `pending_review` since that's a
  missing-data problem, not a proven mismatch.
- **Parts list convention**: the *first* part listed is treated as the main/essential/
  non-replaceable part (its absence routes through the disposition engine's real rules,
  never an auto-restock shortcut); every other listed part is essential/replaceable.
- The tool is fail-open throughout: a bad image URL, a missing category, an unknown category,
  a model/provider failure, or the request budget running out all leave that row `uncertain`/
  `pending_review` with a specific reason recorded — never a guessed verdict, and never
  discarding a return record.

A real 30-row demonstration dataset (real, public, licensed Wikimedia Commons product photos;
every kind of sold-vs-returned ID mismatch; main-vs-side part loss; all 6 category policies;
several malformed-input edge cases) and its live output live under `manual_test_images/`.

## Testing

```sh
uv run returns-manager dev check
```

runs, in order: `ruff check`, `ruff format --check`, `mypy`, `pytest -q` (the full non-live
suite — no real API spend; provider calls are mocked with scripted clients), `reference
validate`, and the repository boundary check. All five gate the submission; `dev check`
exits non-zero if any of them fails.

Docker/Supabase are only needed for the DB-backed tests (tenancy/RLS, the job queue, the
worker's retry/quota-hold logic). Without them, `pytest -q` still runs everything that
doesn't touch the database — most of the suite — and the DB-dependent tests fail with a
clear connection error rather than a silent skip, since `.env`'s `DATABASE_URL` is
pre-filled.

## Evaluation

Two eval runs exist under `../eval/runs/`:

- **`devmini-20260927`** — `returns-manager eval run --dev-mini`, a small explicitly-
  synthetic set that proves the real §21 evaluation statistics machinery (agreement, Cohen's
  kappa, selective prediction, FP/FN, disposition confusion matrix, failure-mode tagging)
  runs correctly end to end. Its own report header says "tooling check only" — it is not a
  reported result.
- **`manual-30row-self-labeled-20260927`** — the same real statistics machinery run against
  real data: 30 units, real licensed photos, real live Gemini judgment calls, the real
  deterministic disposition engine. **Read its `NOTES.md` before `report.md`** — it states
  plainly where this falls short of `RULES.md`'s required eval (single labeller rather than
  two independent ones; 30 units not ≥50; designer-set rather than blind ground truth; one
  logged measurement artifact, F-024) and which numbers in `report.md` are still real signal
  despite that (completeness agreement, condition failure-mode counts, the disposition
  confusion matrix).

No formal, independently-labeled sealed eval set exists yet (`eval/sealed/` and
`eval/labels/` are both empty; `returns-manager eval run` refuses to fabricate one on its
own). That gap needs real human labelling effort, not more code.

## What's honestly still open

- Four findings remain open and unfixed, documented rather than hidden: an over-length
  model field only caught after the fact by local schema validation (F-018), an intermittent
  battery/label misread that a prompt fix reduced but did not eliminate (F-019), no
  duplicate-photo detection in the standalone batch tool (F-020), and the batch tool's
  `identity_match` output column being the carried-forward catalog value rather than the
  model's own read of the returned photo (F-024). Full detail in `../build-log.md`'s
  Findings table.
- **F-023** (closed, but worth knowing about): a documented SDK shape for `tool_choice`
  turned out to be rejected by the live Gemini API even though it matched the installed
  SDK's local type stubs — found via a live batch run, fixed, and logged as a reminder that
  reading the installed source is necessary but not sufficient; a live call is what actually
  proved it.
