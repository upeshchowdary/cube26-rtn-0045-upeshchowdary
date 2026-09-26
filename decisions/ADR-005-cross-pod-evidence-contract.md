# ADR-005 — Cross-Pod Evidence Contract: Schema, Versioning, and Stability Policy

**Status:** Accepted
**Date:** 2026-09-25
**Author:** upeshchowdary
**Supersedes:** none
**Relevant sections:** §14, §16 (build prompt)

---

## Context

Recovery's agent and any other cross-pod consumer needs to read evidence records produced by the
Returns Manager pod.  The record format must be:

1. **Stable** — a consumer written today can still parse records written in 6 months without
   code changes.
2. **Schema-validated** — schema drift is caught before it ships, not by consumers in production.
3. **Honest** — the integrity claim must not overstate tamper-evidence (see ADR-007).
4. **No floats in hashed payloads** — the JCS canonicalizer rejects floats (§13.1); all numeric
   fields in hashed documents use integers (basis points, minor units) or strings.

---

## Decision

### Schema

We maintain a **single Pydantic model** (`contract.models.EvidenceRecord`) as the source of truth.
The JSON Schema (`evidence-record.v1.schema.json`) and flat-view schema are generated from it with
`contract build`.  Both schemas are committed and reviewed on every PR that touches the contract.

### Two-level layout (§14.2)

```
{
  // Fixed contract — field names and types are guaranteed stable
  "record_id": "...",
  "schema_version": "1.0.0",
  "organization_id": "...",
  "client_id": "...",
  "agent": "returns_manager",
  "subject": { "unit_id", "return_id", "order_id", "sku", "asin" },
  "captured_at": "...",
  "operator_label": "...",
  "images": [...],
  "checks": [{ "check_key", "verdict", "confidence_bp", "detail",
               "model_version", "latency_ms" }],
  "outcome": { "decision", "decided_by", "decided_at" },
  "overrides": [...],
  "status": "...",
  "content_hash": "sha256:...",
  // Extensions — richer detail; may grow over minor versions
  "extensions": {
    "returns": { ... all detail fields ... }
  }
}
```

`record_id` and `captured_at` appear at both levels by design — cross-pod consumers can read them
from the top level without traversing `extensions`.  This is the only documented exception to the
no-duplication rule.

### Confidence as basis points

All `confidence_bp` fields are integers 0–10000 (basis points).  The 0.00–1.00 display value
is derived as `round(confidence_bp / 10000, 2)`.  This is required by §13.1 (no floats in
hashed payloads); confidence is always stored as an integer.

### Versioning

- **Patch** (`1.0.x`): bug fixes, clarifications.  No field is added, renamed or removed.  Old
  consumers parse new records without change.
- **Minor** (`1.x.0`): additive changes inside `extensions.returns`.  No fixed-level field is
  changed.  Old consumers continue to read the fixed level; new consumers may read extensions.
- **Major** (`x.0.0`): breaking change; new consumers required.  Must be flagged in the build log
  and surfaced to the organiser.

Consumers must accept **any patch or minor release** within the major version they target.

### Stability guarantees

1. `checks[*].check_key` values in the fixed set (`FIXED_CHECK_KEYS`) are never renamed or
   removed without a major version bump.
2. `outcome.decided_by` is never a raw model name; it is always `rules_engine@<version>`,
   `operator:<label>`, `reviewer:<label>`, or `deterministic_engine`.  Model names never appear.
3. `extensions.returns.integrity.claim` is the ADR-007 verbatim sentence and is never shortened.
4. `schema_version` in every record matches the version of the Pydantic model that wrote it.
5. `content_hash` = `"sha256:" + SHA-256(JCS(record without content_hash))`.  No floats are
   allowed in the hashed document (enforced by `canonical.jcs`).

### Flat view

The flat view CSV (`§14.3`) always starts with the 15 official column headers in the exact order
documented in the build prompt.  Additional columns may be appended to the right.  The flat view
is a lossy projection — consumers needing the full evidence use the JSON record.

### MCP server

The read-only MCP server (`mcp serve`) exposes 4 tools:
- `get_return_evidence` — same document as REST `GET /api/v1/units/{id}/return-evidence`.
- `list_return_evidence` — same as REST `GET /api/v1/evidence/export`.
- `verify_return_chain` — same as REST `GET /api/v1/units/{id}/chain/verification`.
- `explain_return_decision` — lightweight textual explainer (full model-based explainer: P14).

MCP responses are byte-identical to REST responses for the same org and unit.

### Access control

Recovery's agent is issued an API key with scope `evidence:read` and one org only.  The key
grants `Permission.EVIDENCE_READ` and `Permission.PHOTO_URL`.  No write access is ever granted to
cross-pod consumers via this mechanism.

---

## Consequences

- Contract tests `T-CON-01` through `T-CON-18` fail the CI if any stable guarantee is violated.
- `contract build` must be re-run and the generated files committed whenever the Pydantic model
  changes.
- The MCP server is optional infrastructure: it requires `uv add mcp` and a running DB.  The
  CLI command exits with a clear error if the package is absent.
- The flat CSV header prefix is tested against `OFFICIAL_CSV_COLUMNS_15`; it must not be changed
  without a major version bump and a build-log finding entry.

---

## Rejected alternatives

| Alternative | Rejection reason |
|---|---|
| Use Avro/Protobuf as primary schema | External dependency; harder to inspect; JSON is the contract format specified in §14 |
| Store `confidence` as float (0.00–1.00) in document | Violates §13.1 (no floats in hashed payloads); basis points are integer and exact |
| Keep extensions flat in the top level | Violates §14.2 two-level requirement; breaks the no-duplication invariant |
| Serve MCP without API key auth | Too permissive; recovery's agent already has a scoped key per §6.1 |
