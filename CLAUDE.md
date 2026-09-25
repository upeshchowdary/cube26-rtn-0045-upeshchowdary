# CLAUDE.md · Returns Manager (Cube Buildathon 04)

**Mission:** from 2–3 phone photos of a returned product plus the seller's own catalogue, order, parts list
and Amazon's published condition guidelines, record an evidence-backed verdict on identity, completeness
and condition, and let deterministic rules (never the model) compute one of restock / refurbish / liquidate /
dispose, with "uncertain" and human review as first-class outcomes.

The full specification is the build prompt, kept **outside** this repo at
`../RETURNS_MANAGER_PROMPT_PART1_BACKEND.md` (Part 1, backend). Section numbers (§) below refer to it.

## Where things live (fork root; see finding F-007)

| Path | What |
|---|---|
| `build-log.md` | dated plan / changed / failed / evidence / next; `## Findings`, `## Open questions` |
| `decisions/` | ADRs (`ADR-000-template.md`); required ADR-001…008 |
| `findings/` | `F-###-slug.md`, mirrored as GitHub Issues labelled `finding` |
| `contract/` | evidence-record schema, flat view, examples, OpenAPI, MCP tool docs |
| `reference/` | product cards, rubric snapshots, policies, category map, rules, quality gate, pricing |
| `fixtures/` | dev fixtures only (never eval data) |
| `eval/` | `sealed/` and `labels/` are **off-limits** except to `returns-manager eval run` |
| `anchors/` | ledger anchors |
| `scripts/check_boundary.py` | local boundary check (branch name, organiser files, forbidden files, 5 MB cap) |
| `agent/` | Python package `returns_manager` (`src/`), `migrations/`, `prompts/`, `tests/` |
| `.env.example` | every configuration variable; the real `.env` is git-ignored |

Organiser-owned files are never modified: `.github/`, `data/`, `submissions/`, root `.gitignore`,
`README.md`, `RULES.md`, `GITHUB-GUIDE.md`.

## Hard rules

- **Repo boundary and branch:** work on branch `upeshchowdary`, never commit to `main`; one PR per phase
  into the fork's `main`. Run `python scripts/check_boundary.py` before every push.
- **No secrets** in git, logs or messages: `.env` is ignored; gitleaks runs in pre-commit; secrets are
  `SecretStr`. If a key leaks, revoke it; deleting the commit does not help.
- **Tenancy (Rule 1):** RLS enabled **and forced** on every tenant table; policy
  `org_id = NULLIF(current_setting('app.org_id', true), '')`; tenant set per transaction with
  `set_config('app.org_id', $1, true)`; open DB transactions only via `db.tenant.transaction(org_id)`.
  The app connects as `rm_app_login` (NOSUPERUSER, NOBYPASSRLS) and **refuses to boot** if its role can
  bypass RLS. Only the four `SECURITY DEFINER` functions of §6.4 cross tenants; adding one needs an ADR and
  the human's approval. Cross-org access answers 404. Storage keys are uuid4; photos only via short-TTL
  signed URLs issued after an RLS-scoped ownership check; never log a signed URL.
- **Rule 2:** one Judgment session per inspection carrying all checks in one structured output; normally
  one request; at most `RM_MAX_ROUND_TRIPS` (default 2) requests including tool round trips. Escalation and
  audit are separate full re-judgments, never per-check calls. Requests per inspection are measured.
- **Fail open:** photos and the return row are stored before any model call. Any model/provider failure
  leaves the return `pending` or `needs_attention` with a reason. A failure never produces a pass, a
  guessed grade or an auto-disposition. Nothing blocks the operator.
- **Uncertain first:** `uncertain` is a verdict with a reason code, never a low-confidence pass.
- **Look rules up:** grades, unacceptable conditions and category rules come from extracted, hashed
  source documents; never from model memory or the synthetic sample CSV.
- **The model never decides the disposition** (no disposition field in its output) and **never invents
  references**: every component, feature, grade, rubric quote and photo alias is checked by code.
- **Gemini sessions are stateful:** chain turns with `previous_interaction_id`; never rebuild, edit or
  reorder history; re-send tools/config identically each turn; never switch models mid-session.
- **No sampling parameters** (`temperature`, `top_p`, `top_k`). Tool choice mode is `auto` only; never force
  a tool call.
- **Never request or persist thoughts** (thinking content), and never ask the model to explain its reasoning.
- **The daily request-quota guard is never bypassed.** Every Gemini call first takes a token from
  `llm/quota.py`. Development and tests use **replay cassettes**, not live quota; only P5 smoke tests, the
  §18.5 measurement and the eval spend real requests.
- **Eval data is off-limits:** never read, open, display, sample or tune against `eval/sealed/` or
  `eval/labels/`.
- **Spend guards:** paid spend is $0 (free tier). Any bulk model work runs a quota/spend preflight and
  refuses without the human's explicit flag.
- **Every number has its method next to it** (and `n`, and window).
- **Never guess an SDK signature:** read the official docs or the installed package source; if they
  contradict the prompt, the docs win and the contradiction is logged as a finding.
- **No business logic in FastAPI routes or CLI commands**; they call the service layer.

## How to run

```sh
cd agent
uv sync                                   # Python 3.12, exact pins from uv.lock
npx supabase start                        # local Supabase (Docker Desktop must be running)
uv run returns-manager db migrate
uv run returns-manager seed demo
uv run returns-manager dev check          # ruff + mypy + pytest (non-live) + reference validate + boundary check
```

Exit codes: 0 ok · 1 failure · 2 usage error · 3 verification failed · 4 spend guard refused · 5 configuration invalid.

## Definition of done per phase

See §23 of the build prompt (acceptance criteria per phase P0–P14) and §27 (backend definition of done).
A phase is done only when its acceptance tests pass, `dev check` is green, and `build-log.md` records
what changed, what failed and the evidence.

## Forbidden language (§24, verbatim)

| Never say | Say instead |
|---|---|
| tamper-proof, immutable, blockchain-secured | "tamper-evident within the database (hash-chained); not immutable" + the ADR-007 sentence |
| fraud detected, fraudulent customer | "identity mismatch", "possible product swap — requires review" |
| counterfeit (as a verdict) | "counterfeit indicators observed — requires review" |
| the AI decided the disposition | "the rules engine computed the disposition from the inspection evidence" |
| guaranteed, 100% accurate, never wrong | the measured number with its method, n and CI |
| real-time | the measured latency (p50/p95) |
| production-ready, enterprise-grade | what is tested, and how |
| certified, Certified Refurbished, Renewed, Amazon-approved, Amazon-compliant | "graded against Amazon's published condition guidelines (snapshot <id>, <verification status>)" |
| learns from overrides, self-improving | "overrides are recorded as labelled data; no automatic retraining" |
| understands, sees like a human | "the model reported …" |
| works perfectly, fully functional | "functional test not performed" |
| no damage (when not observed) | "no damage observed in the provided photos" |
| missing (when not visible) | "not visible in the provided photos" |
| secure (unqualified) | name the control ("row-level security forced per org; signed URLs, 5-minute TTL") |
