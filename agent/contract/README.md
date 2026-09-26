# Returns Manager — Cross-Pod Evidence Contract (v1)

This directory is the interoperability surface for Round 3: it is the only thing another
pod (Recovery, Prep, Pack, Receiving) should ever need to read to consume Returns Manager
evidence. It is generated from, and validated against, the Pydantic models in
`src/returns_manager/contract/` — see ADR-005 for the design rationale and stability policy.

## Files in this directory

| File | What it is | How it's produced |
|---|---|---|
| `evidence-record.v1.schema.json` | The fixed evidence contract (JSON Schema draft 2020-12) | `returns-manager contract build` |
| `return-evidence-flat.v1.schema.json` | Schema for the flat (CSV) view | `returns-manager contract build` |
| `flat-columns.v1.csv` | The flat view's column list, in official order | `returns-manager contract build` |
| `openapi.json` | The full REST API surface | `returns-manager openapi export --out contract/openapi.json` |
| `mcp-tools.md` | The 4 read-only MCP tools, their inputs/outputs and auth | hand-authored, kept in sync with `src/returns_manager/mcp_server.py` |
| `examples/` | One example evidence record per representative scenario | hand-authored / exported from real records |
| `CHANGELOG.md` | Contract version history | hand-authored |

Regenerate the first three with `uv run returns-manager contract build` (writes here by
default) whenever `contract/models.py` or `contract/schema.py` changes, and commit the
result — these files, not the Python source, are what a consumer actually reads.

## Semantics

Every evidence record has **exactly** the fixed top-level fields named in §14.2 of the build
prompt (`record_id`, `schema_version`, `organization_id`, `client_id`, `agent`, `subject`,
`captured_at`, `operator_label`, `images`, `checks`, `outcome`, `overrides`, `status`,
`content_hash`), plus `extensions.returns` for everything Returns-specific. The two
exceptions to "no field is duplicated between the fixed level and `extensions`" are
`record_id` and `captured_at`, which are readable at both levels by design (§14.2 note).

- **`verdict`** is one of `PASS` / `FAIL` / `UNCERTAIN` (uppercase). `UNCERTAIN` is never a
  disguised low-confidence `PASS` — see the "uncertain is a valid verdict" rule in `RULES.md`.
- **`confidence`** in the JSON record is a display value (0.00–1.00, two decimals); the
  hashed document underneath stores confidence as `confidence_bp` (integer basis points,
  0–10000) because the canonical hashing algorithm (RFC 8785 JCS) rejects floats.
- **`outcome.decided_by`** is never a raw model name. It is `rules_engine@<version>`,
  `operator:<label>`, `reviewer:<label>`, or `deterministic_engine`. The model decides no
  disposition; the deterministic engine does (see `CLAUDE.md` "the model never decides the
  disposition").
- **`content_hash`** is `"sha256:" + hex(SHA-256(JCS(record without content_hash)))`. It
  equals the internal `document_sha256`. It is **tamper-evident within this database**
  (hash-chained; the previous record version and the org ledger both reference it) — it is
  **not** immutable, blockchain-secured, or independently verifiable outside this system.
  See ADR-007 for the exact wording this project commits to and why stronger language is
  not used.

## Join keys

- Primary join key across pods: `unit_id` (stable across the item's lifecycle).
- `record_id` is this system's opaque record identifier (the official `RTN-####` stage
  prefix); treat it as opaque, not as a cross-pod key.
- `organization_id` / `client_id`: `organization_id` is the tenant that owns the data.
  `client_id` is who the work is done *for* — equal to `organization_id` unless this
  deployment is a prep center or 3PL working on behalf of a seller (§14.2). Until the
  organisers publish an exact definition, this repo defaults `client_id = organization_id`
  and logs the assumption (see `build-log.md`, open question OQ-1).
- `order_id`, `ordered_sku`, `ordered_asin` come from the order Returns received the unit
  against; `actual_sku` (under `extensions.returns`) is populated only when identity
  resolved to a different SKU than ordered.

## How to authenticate

Two consumer surfaces, one credential model:

- **REST**: `Authorization: Bearer <JWT>` (a Supabase-authenticated user) or
  `X-API-Key: rmk_<env>_<...>` (a machine key). Either resolves to a `Principal` scoped to
  exactly one org.
- **MCP** (`returns-manager mcp serve`): `Authorization: Bearer <api key>` on every request.
  The same `rmk_<env>_<...>` key format and the same scope check as REST — there is no
  separate MCP-only credential. The key's org scopes every call; **no MCP tool accepts an
  `org_id` argument**, so a client cannot ask for another organization's data by supplying
  a different value.

Request a key with `returns-manager keys create --org <org_id> --scope evidence:read --name <consumer>`.
The plaintext is shown once, at creation, and never stored or logged. `evidence:read` grants
`EVIDENCE_READ` and `PHOTO_URL` only — never write access.

## Versioning policy (ADR-005)

- **Patch** (`1.0.x`): fixes/clarifications; no field added, renamed or removed.
- **Minor** (`1.x.0`): additive fields inside `extensions.returns` only. The fixed contract
  never changes on a minor bump.
- **Major** (`x.0.0`): a breaking change (field removed, renamed, or its meaning changed).
  Served as `/api/v2` alongside `/api/v1`; `/api/v1` is never broken during the transition
  (§14.6, §25 anti-pattern 22).

## Supports / contradicts / silent — reading our signals (§14.4)

Guidance for a consumer (e.g. Recovery) deciding what a Returns Manager record implies
about one of *its own* claims. This is Returns' reading of its own evidence, not a
cross-pod adjudication — Recovery owns its own logic.

| Recovery signal | Returns field | Reading |
|---|---|---|
| `refund_issued_item_not_returned` | `claim_signals.item_not_returned` | `yes` **supports** the claim; `no` (product present, `identity_match = yes`) **contradicts** it; `uncertain` or no finalized record (404) is **silent** |
| a different item came back | `claim_signals.wrong_item_returned` + `identity.observed_identifiers` / `subject.actual_sku` | `yes` is evidence of a swap or mismatch — Returns reports what was observed, not who is at fault |
| item came back damaged | `claim_signals.returned_damaged` + `condition.observations` | Returns provides *observations*, never *attribution* (who caused the damage is not observable in photos) |
| any claim | `status != "finalized"` | Treat as **silent** unless the consumer explicitly chooses to read pending/in-progress state (`include_pending=true`) |

## Consumer access

- REST: see `openapi.json` for the full surface; the evidence-specific routes are
  `GET /api/v1/units/{unit_id}/return-evidence`,
  `GET /api/v1/units/{unit_id}/return-evidence/history`,
  `GET /api/v1/evidence/export?since=&format=jsonl|csv`.
- MCP: see `mcp-tools.md`.
- Each consuming pod gets its own scoped API key — never a shared key.

## Agreeing the contract with another pod

Before another pod builds against this contract, record the agreement here:

| Pod | Contact | Date | Contract version agreed | Notes |
|---|---|---|---|---|
| Recovery | *(not yet contacted — Round 2 is a solo build; no other pod exists to agree with yet)* | — | 1.0.0 | Placeholder; fill in during Round 3 pod formation |

Until a row is added above, treat this contract as a **draft interoperability proposal**,
not a bilaterally agreed interface — do not claim otherwise in submission documents.
