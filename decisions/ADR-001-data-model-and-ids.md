# ADR-001 Data model and identifiers
Status: accepted
Owner: upeshchowdary
Date: 2026-09-25
Revisit by: 2026-11-01
Reversibility: irreversible — changing ID schemes or primary key types requires database and schema migrations

## Decision (one paragraph: what)

All entity identifiers in Returns Manager are strongly-typed, human-readable strings composed of a 3–4 letter lowercase prefix and Crockford Base32 encoded random entropy (e.g. `ret_`, `pho_`, `rec_`, `job_`, `key_`, `sub_`), generated via `returns_manager.ids.new_id()`. Tenant identifiers follow lowercase alphanumeric conventions (`^[a-z0-9][a-z0-9_]{1,62}$`). Content hashes across evidence records, photos, product cards, and audit chain entries are computed exclusively using SHA-256 over Canonical JSON (RFC 8785 / JCS) representations. Data structures adhere strictly to the immutable append-only pattern within Postgres schema `rm`, wherein finalized evidence records and event chain entries are never updated or deleted in place, but superseded by incrementing integer version counters.

## Why

- **Human-Readable & Safe Identifiers**: Prefixing IDs (`ret_...`, `pho_...`) prevents accidental transposition in API parameters and logging while ensuring URL and header safety without percent-encoding.
- **Canonical Hashing (RFC 8785)**: Cryptographic audit chains and tamper-evident ledgers require deterministic serialization regardless of key ordering or whitespace formatting across different JSON engines.
- **Append-Only Immutability**: Historical evidence and compliance audits demand that prior inspection states remain reconstructible; supersession ensures full traceability without losing original observations.
- **Type Safety**: Pydantic models and database schema constraints validate prefix and format at the API boundary before hitting business logic.

## Rejected alternatives (and why)

- **Raw UUIDv4 strings**: Lack human-inspectable type indicators, making logs and API debugging error-prone when distinguishing between photo IDs, return IDs, and job IDs.
- **Auto-incrementing integers**: Vulnerable to enumeration attacks, leak organizational return volumes across tenants, and complicate distributed offline generation.
- **In-place record mutation (UPDATE)**: Destroys the historical trail required by cross-pod contracts and audit compliance.

## Consequences

- All service and repository functions accept and return typed identifier strings.
- Hashes must always be calculated via `canonical_json_hash()` rather than standard `json.dumps()`.
- Records are versioned (`version: int >= 1`), with `evidence.superseded` events emitted when corrections or human overrides occur.
