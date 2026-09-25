# Build log · Returns Manager (Cube Buildathon 04)

Owner: upeshchowdary · Branch: `upeshchowdary` (merged into `main` by PR at the end of each phase)

Every entry is dated and follows *plan / changed / failed / evidence / next*. Where a number appears, the
method is written next to it. Sections `## Findings` and `## Open questions` are at the bottom.

---

## 2026-09-25 · Pre-code restatement (required by the build prompt before any code)

### Rule 2 (batch model calls), as I will implement it
- One inspection of one returned unit is **one Judgment session**. That session answers *every* check at
  once (unit presence, identity, completeness per component, condition, observed state, retake needs) in a
  single structured JSON output. There is never a model call per check.
- In the normal case the session is exactly **one** API request. The model may use one of three read-only
  "exception tools" (crop a photo region, fetch more reference views, fetch a look-alike sibling SKU); each
  tool round trip is one extra request. The total per session is capped at `RM_MAX_ROUND_TRIPS` (default
  **2** on the Gemini free tier: the first request plus at most one tool round trip).
- Escalation and audit are *separate, complete* re-judgments (again all checks in one output), run only
  when a trigger fires (escalation) or a sample is drawn (audit; 100% of the eval set only). They are never
  per-check calls.
- I will measure and report mean and p95 requests per inspection, tool calls per inspection, tokens by
  type, cached-token share, paid-equivalent cost, and requests used per day against the free quota.
  Target: mean ≤ 1.2 requests per inspection (see Open question OQ-3 on the 1.2 vs 1.3 wording).

### Tenancy mechanism, as I will implement it
- All tenant data lives in Postgres schema `rm`. Every tenant table has `org_id text NOT NULL CHECK
  (org_id <> '')`, and has row-level security **enabled and forced** (so even the table owner is subject to
  it) with one policy: rows are visible/writable only when `org_id = NULLIF(current_setting('app.org_id',
  true), '')`.
- The tenant is set **per transaction**: every unit of work is one explicit transaction that starts with
  `set_config('app.org_id', <org>, true)` (the `true` makes it transaction-local, so it cannot leak to the
  next user of a pooled connection). If no org is set, the `NULLIF` turns the empty setting into NULL and
  the policy matches **nothing**: missing context fails closed, it never fails open.
- The API, worker, MCP server and CLI connect as `rm_app_login`, a role that is NOSUPERUSER and
  NOBYPASSRLS. At boot each process checks `rolsuper`/`rolbypassrls` for its own role and **refuses to
  start** if either is true, because a green isolation test under a bypass role proves nothing.
- Application code can open a DB transaction only through one helper, `db.tenant.transaction(org_id)`;
  a lint test fails if raw pool usage appears outside `db/`.
- Only four audited `SECURITY DEFINER` functions may cross tenants (claim next job, resolve API key,
  look up a user's memberships, reap expired leases). Adding a fifth needs an ADR and the human's approval.
- Photos live in private storage buckets under unguessable keys `org/{org_id}/returns/{return_id}/{uuid4}.{ext}`.
  Nobody gets a storage URL except through the backend, which first confirms ownership with an RLS-scoped
  query and then issues a signed URL valid for 300 s. Another org's resource answers **404**, not 403.

### The four accountability controls
1. **Scoped credentials** — every human is a Supabase-authenticated member of an org with one role
   (operator / reviewer / admin); every machine client gets its own API key limited to named scopes and
   one org (Recovery's agent: `evidence:read` on one org only).
2. **Audit trail** — a per-unit hash-chained event log, a per-org ledger of finalised records and system
   events, and versioned evidence records, so "who asked, what was decided, on what evidence" can be
   reconstructed later.
3. **Thresholds** — `dispose` always needs a second-person sign-off; any non-restock route on a
   high-value item needs sign-off; the signer can never be the operator who captured the return.
4. **Kill switch** — `rm.system_controls` rows (`auto_disposition_enabled`, `model_calls_enabled`,
   `audit_enabled`, `escalation_enabled`), global or per org, admin-only, reason required, recorded in the
   org's system chain, and each one exercised by a drill test.

### Forbidden language (§24, verbatim)

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

---

## 2026-09-25 · Setup decisions (with the human, before P0)

- **Model provider:** Google Gemini, Developer API free tier (the prompt was revised from Anthropic to
  Gemini). Key stored only in the git-ignored `.env`. Verified 2026-09-25 by listing models
  (`GET /v1beta/models`, no generation quota used): `gemini-3.8-flash`, `gemini-3.6-flash`,
  `gemini-3.1-flash-lite` and `gemini-3-flash-preview` are all available to this key.
- **Repository layout:** the repo root of the participant's own fork, not `submissions/<user>/`
  (human's decision; see finding F-007). Organiser-owned files are never modified (see
  `scripts/check_boundary.py`).
- **Location:** clone at `C:\Users\UPESH CHOWDARY\Desktop\cube26-rtn-0045-upeshchowdary-main\cube26-rtn-0045-upeshchowdary`,
  outside OneDrive (OneDrive is full, and syncing a `.venv` causes file locks).
- **Git:** work on branch `upeshchowdary`; one PR into the fork's `main` per phase, merged after the
  human approves. Repo-local `core.autocrlf=false`, `core.eol=lf`, plus `.gitattributes`, because the
  global `autocrlf=true` had checked files out as CRLF.
- **Supabase:** local stack via Docker (`supabase start`) for P1. Hosted project later for the demo.
- **Organiser materials** (domain brief, sandbox, shared catalogue, worked example, exact contract
  schema, target marketplace): not available yet → open questions OQ-1, OQ-2.

---

## 2026-09-25 · P0 Compliance and skeleton

**Plan**
1. `.gitattributes` (LF, binaries), nested `.gitignore` files; the organiser's root `.gitignore` stays as is.
2. `.env.example` listing every §5 variable with a placeholder and a comment; the real `.env` is ignored.
3. `agent/pyproject.toml` (Python 3.12, uv, exact pins in `uv.lock`), package `returns_manager` under `agent/src/`.
4. `config.py` (pydantic-settings; validated at start-up; secrets never printed), `errors.py` (exit codes).
5. Typer CLI `returns-manager` with the §20 command tree; unbuilt commands say which phase builds them and exit 1.
6. `scripts/check_boundary.py`: the CI guard's intent adapted to the fork-root layout.
7. `CLAUDE.md` (§22), `decisions/ADR-000-template.md`, `findings/F-007-*.md`.
8. `.pre-commit-config.yaml`: ruff, gitleaks, large files (5 MB), boundary check; install the hooks.
9. Tests: CLI help, exit codes, config validation, boundary-check logic. Run `returns-manager dev check`.

**Changed**
- Python 3.12 project in `agent/` (uv; every dependency pinned with `==` in `pyproject.toml` and exactly in
  `uv.lock`). Package `returns_manager` with `config.py` (pydantic-settings; every §5 variable; secrets as
  `SecretStr`; `require(...)` → exit 5 naming only the missing variables), `errors.py` (exit codes 0–5, §20),
  and the Typer CLI `returns-manager` with the full §20 command tree. Unbuilt commands print
  "`<cmd>` is not built yet (planned for phase Pn)" and exit 1; `dev check` is real.
- `scripts/check_boundary.py` (standard library only): branch must be `upeshchowdary` (never `main`); no
  change to organiser-owned paths; no `.env`/PDF/key files; 5 MB cap per file.
- `.pre-commit-config.yaml`: large files (5 MB), merge conflicts, private keys, LF endings, TOML/YAML,
  ruff check + format, gitleaks, boundary check. Organiser files are excluded from every fixer.
- `.gitleaks.toml`: default rules + `google-api-key-aq` for `AQ.`-prefixed Google keys.
- `.gitattributes` (LF everywhere; binaries; `data/** -text` keeps organiser data byte-exact),
  `agent/.gitignore`, `.env.example`, `CLAUDE.md`, `decisions/ADR-000-template.md`, finding F-007.

**Failed, and what the evidence showed**
- `.env.example` first used inline comments (`KEY=   # note`). python-dotenv parses that as the value
  `"# note"`, so empty variables such as `DATABASE_URL` would have loaded a comment as their value.
  Caught by `test_env_example_parses_and_matches_prompt_defaults`. Fixed by putting every comment on its own
  line; guarded by `test_env_example_values_never_swallow_comments`.
- Typer 0.27.2 no longer depends on `click` (it vendors it as the private `typer._click`). The CLI runs Typer
  in standalone mode and maps `SystemExit` / our own errors to exit codes instead of importing click.
- Intermittent native crashes (`0xC0000005` / segfault) of `ruff.exe`, Go's `asm.exe` and `git.exe`, every
  time launched from the Git Bash shell; the same commands succeed from PowerShell. Workaround: heavy tool
  runs go through PowerShell. The upstream gitleaks hook compiles gitleaks from Go source and crashed twice
  the same way, so the hook uses the prebuilt gitleaks v8.30.1 Windows binary (release asset, SHA-256
  verified against `gitleaks_8.30.1_checksums.txt`), installed at `~/.local/bin/gitleaks.exe`.
- gitleaks' default rules caught an `AQ.`-prefixed key only through `generic-api-key`, i.e. only next to a
  word like `API_KEY`. Added the `google-api-key-aq` rule; a bare key in a URL is now detected (tested with
  a fake key), and `gitleaks dir .env` flags the real key (1 finding).
- The line-ending fixer rewrote `data/returns_sample.csv` (organiser-owned, committed with CRLF); the
  boundary check blocked it. Reverted; organiser paths are now excluded from fixers and `data/** -text` set.

**Evidence (acceptance criteria, §23 P0)**
- `returns-manager --help` exits 0 and lists every §20 group (`test_help_exits_zero_and_lists_command_groups`).
- `returns-manager dev check` → ruff ok, ruff format ok, mypy ok (7 source files), pytest **33 passed**,
  reference validate skipped (P2), boundary check ok (branch `upeshchowdary`, 26 changed files, none
  organiser-owned).
- `pre-commit run --all-files`: all 10 hooks passed, twice in a row (second run = no changes).
- `pre-commit install` → `.git/hooks/pre-commit` installed.

**Next:** commit, push `upeshchowdary`, open the P0 PR into `main`; then P1 (needs Docker Desktop running).

---

## 2026-09-25 · P1 Security Foundation

**Plan**
1. Implement DB schema migrations 0001–0003 (roles, RLS/tenancy, intake tables).
2. Implement `db/pool.py` (`UnsafeDatabaseRole` boot check), `db/tenant.py` (`transaction` helper, `validate_org_id`), `db/migrate.py` (checksummed migration runner).
3. Implement `security/` (roles, api_keys, auth_jwt, controls), `storage/` (photos, signed_urls, service_client), `canonical/` (JCS/RFC 8785), `seed/demo.py`.
4. Write static unit tests (`test_security_static.py`, `test_authorization_matrix.py`, `test_canonical.py`, `test_migrations_and_keys_layout.py`) — no DB.
5. Write DB security tests `T-SEC-01…08` (`test_db_security.py`) — need `supabase start`.
6. Fix all ruff/mypy/pytest issues; run `returns-manager db migrate` + `seed demo` against local Supabase.
7. Draft `ADR-003-tenancy-mechanism.md` and `ADR-004-identity-and-auth.md`; update this log; commit/push; open P1 PR.

**Changed**
- `api/app.py`: Changed `PhotoStorage` initialization guard from `settings.supabase_service_role_key` to
  `settings.supabase_url`. This keeps the service-role key strictly confined to `storage/` — no other
  module even reads it as a presence check. T-SEC-08 in the static suite now passes without a carve-out.
- `migrations/0001_roles_and_schema.sql`: Reworded comment "No role created here has BYPASSRLS" → "All
  roles carry NOBYPASSRLS explicitly" so the regex `(?<!NO)BYPASSRLS` never fires on a comment line.
- `tests/unit/test_security_static.py`:
  - `T-SEC-08`: Removed the `api/app.py` carve-out (now cleanly not needed). Added human-readable failure
    message to the offenders assertion.
  - `T-SEC-05` (tenant table count): Changed `>= 7` to `>= 6` — P1 creates exactly 6 tenant tables
    (`memberships`, `api_keys`, `returns`, `return_photos`, `operator_observations`, `inspection_jobs`);
    the 7th is `organizations`, which has `org_id` as a PRIMARY KEY, not as a `NOT NULL` foreign column.
    Threshold grows as P2+ migrations add tables. Added descriptive assertion message.
  - Fixed E501 on line 57 (split long list-comprehension condition across lines).
- `tests/conftest.py`: Fixed E501 on `pytest_asyncio_loop_factories` signature (split to two lines).
- `tests/unit/test_authorization_matrix.py`:
  - Fixed PT011: added `match=r"not a valid Scope|at least one scope"` and `match="at least one scope"`.
  - Fixed RUF043: used raw string for alternation pattern.
  - Let ruff format reformat the parametrize tuples (no logic change).
- `tests/unit/test_canonical.py`: Let ruff format reformat the long golden-vector tuples.
- `tests/unit/test_db_security.py` (new): DB security tests `T-SEC-01…08`. All marked `@pytest.mark.db`;
  all skip gracefully when `DATABASE_MIGRATOR_URL` is not set (i.e. Supabase isn't running).
  Fixtures use fresh unique org IDs per run (no DELETE grants exist). Scope: function (not module)
  to avoid pytest-asyncio ScopeMismatch under `asyncio_mode=auto`.
- `decisions/ADR-003-tenancy-mechanism.md` (new): Decision, rationale, rejected alternatives, and
  consequences for the per-transaction GUC tenancy model.
- `decisions/ADR-004-identity-and-auth.md` (new): Decision, rationale, rejected alternatives, and
  consequences for JWT + scoped API key authentication.

**Failed, and what the evidence showed**
- First draft of `test_db_security.py` used `assert_photo_owner` (non-existent function in `signed_urls.py`)
  and `Control.AUTO_DISPOSITION_ENABLED` (wrong enum value; correct is `Control.AUTO_DISPOSITION`).
  Caught before any DB run; corrected to use actual functions and enum values.
- `test_db_security.py` fixture `db` set to `scope="module"` initially, causing `ScopeMismatch` in
  pytest-asyncio 1.4 under `asyncio_mode=auto` (module-scoped async fixture conflicts with function-scoped
  event loop). Corrected to `scope="function"` — `migrate()` is idempotent so the extra overhead is zero.
- `app.py` originally guarded `PhotoStorage(settings)` with `settings.supabase_service_role_key` — this
  referenced the secret outside `storage/`. T-SEC-08 needed a carve-out. Root-cause fixed: guard uses
  `settings.supabase_url` (a plain URL, not a secret). The secret now appears only in
  `storage/service_client.py` and `config.py`.

**Evidence (acceptance criteria, §23 P1)**
- `ruff check src tests` → **All checks passed!** (44 files)
- `ruff format --check src tests` → **44 files already formatted**
- `mypy --config-file pyproject.toml` → **Success: no issues found in 33 source files**
  (unused-section notes for `disposition.*`, `evidence.*`, `judgment.*` are expected — those modules
  are built in later phases)
- `pytest -q` → **76 passed, 8 skipped** (8 db tests skip because Supabase is not yet running;
  `pytest -m db` will run them once `supabase start` completes)
- `decisions/ADR-003-tenancy-mechanism.md` and `decisions/ADR-004-identity-and-auth.md` written.

- Local Supabase running via Docker on port 54322/54321.
- `returns-manager db migrate`: applied 0001, 0002, 0003. Migrator connects as `supabase_admin:postgres` because `postgres` role on local Supabase has `rolsuper = f` and cannot execute `ALTER ROLE rm_app_login WITH LOGIN PASSWORD`.
- `returns-manager seed demo`: seeded 2 orgs (`org_demo_alpha`, `org_demo_bravo`), 7 users; credentials in `.env.demo-users`.
- `pytest -m db -v`: all 8 DB security tests (`T-SEC-01` through `T-SEC-08`) **passed**.
- `pytest -q`: **84 passed, 0 skipped, 0 failed** in 2.12 s.
- `returns-manager dev check`: ruff ok, ruff format ok, mypy ok, 84 tests passed, boundary check ok.
- P1 Definition of Done met in full.

---

## 2026-09-25 · P2 Reference Data

**Plan**
1. Draft `ADR-006-rubric-source-substitute.md` (amazon.co.uk PDF as unverified substitute for amazon.in) and finding `findings/F-001-condition-guidelines-marketplace.md`.
2. Define Pydantic reference models in `agent/src/returns_manager/reference/models.py` and JSON Schemas in `reference/_schemas/` for all §8 reference data types.
3. Implement RFC 8785 canonical content hashing in `agent/src/returns_manager/reference/hashing.py`.
4. Create `reference/sources.yaml` with external source documents (Amazon UK condition guidelines PDF, SHA-256 `342a3dc2e9cbdec5467ec03417630f1e2466ac3bbf6d7a6965caf871a35e2718`).
5. Implement `returns-manager rubric extract` in `agent/src/returns_manager/reference/extract.py` using PyMuPDF (verified exact quotes for `electronics`, `toys_games`, `home_kitchen`, `pet`, `beauty_topical`, `grocery_ingestible`), generate snapshots, and write `reference/rubrics/active.yaml`.
6. Author category policies in `reference/policies/amazon.co.uk/<category>.yaml` with explicit `source_type` on every field.
7. Author `reference/categories/sku-category-map.yaml` mapping all 10 sample SKUs.
8. Author `reference/rules/disposition-params.yaml`, `reference/quality/quality-gate.yaml`, `reference/pricing/gemini.yaml`, `reference/pricing/fx.yaml`.
9. Author Product Knowledge Cards in `reference/products/<org_id>/<SKU>.yaml` for fixture SKUs across `org_demo_alpha` and `org_demo_bravo`, plus downscaled reference images and `reference/orders/orders-seed.csv`.
10. Implement `returns-manager reference validate` and `reference hash` in `agent/src/returns_manager/reference/validator.py` (verifying JSON schemas, `content_sha256`, and exact substring matching of rubric quotes against extracted PDF pages).
11. Migration `0004_reference_data.sql` and loader `returns-manager reference load` in `agent/src/returns_manager/reference/loader.py` with RLS and isolation.
12. Wire CLI commands, update `dev.py` so `dev check` executes `reference validate`, and write comprehensive unit tests.

---


## Findings

| F-### | date | source | contradiction | impact | our handling | GitHub issue |
|---|---|---|---|---|---|---|
| F-007 | 2026-09-25 | prompt §0.3/§1.1/§4.2 vs RULES.md R2/R3, GITHUB-GUIDE | prompt: build only in `submissions/<user>/` with the PR CI guard; repo rules: build in own fork, no submissions folder or PR | where files live; which boundary check applies | fork-root layout (human's decision); CI-guard intent kept in `scripts/check_boundary.py` | pending |

F-001…F-006 (§26) are verified and filed in the phases that act on them (P2, P6).

## Open questions

- **OQ-1** Organiser materials (domain brief, sandbox, shared catalogue, worked Returns example, exact
  evidence-contract schema): not available as of 2026-09-25. Conservative default: build to the prompt's §14.
- **OQ-2** Target marketplace for condition grading (amazon.in presumed). Must be asked of the organisers
  before P2 finishes; until then the amazon.co.uk PDF is an `unverified_substitute` (F-001).
- **OQ-3** Requests-per-inspection target: §3.4 says mean ≤ 1.2, §27 says ≤ 1.3. Using the stricter 1.2.
- **OQ-4** The prompt's test names still use Anthropic terms ("append-only messages", "refusal", "batch
  pricing"). Mapped to Gemini equivalents: stateful `previous_interaction_id` chaining, safety blocks /
  finish reasons, no batch on the free tier.
- **OQ-5** Eval readiness: a second independent human labeller and ≥10 physical products are not confirmed
  yet. Needed by about day 3 (2026-09-27) given ~18 judgment requests/day on the free tier.
- **OQ-6** Findings are to be mirrored as GitHub Issues labelled `finding`; issues are disabled by default on
  forks. Pending the human enabling issues on the fork.
