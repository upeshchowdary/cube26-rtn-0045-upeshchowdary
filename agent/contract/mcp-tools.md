# MCP tools (§16)

Read-only MCP server for cross-pod agent access. Started with `returns-manager mcp serve
[--host HOST] [--port PORT]` (defaults `0.0.0.0:8001`). Requires the `mcp` package
(`uv add mcp`, already a dependency of this package) and a reachable database.

Transport: streamable HTTP (`mcp.server.mcpserver.MCPServer`, the SDK's v2 API — the
package renamed `FastMCP` to `MCPServer` between v1 and v2; this server targets whatever
is pinned in `pyproject.toml`). Endpoint: `POST /mcp` on the configured host/port.

## Authentication

Every request must carry `Authorization: Bearer <api key>`, where `<api key>` is a
`rmk_<env>_<...>` key created with `returns-manager keys create --scope evidence:read`
— the same key format and the same `security.api_keys.authenticate()` check the REST API
uses. There is no separate MCP-only credential and no OAuth flow.

A request with a missing/malformed header, an unknown/revoked/expired key, or a key
without the `evidence:read` scope is rejected with HTTP 401/403 **before** any MCP message
is processed. The resolved `Principal`'s `org_id` scopes every tool call made over that
connection — **no tool accepts `org_id` as an argument**, so a client cannot read another
organization's data by supplying a different value; there is nothing to supply.

## Tools

All four tools are read-only (no write tools are exposed over MCP — least privilege for
agent-to-agent traffic, per §16 and anti-pattern §25.21).

### `get_return_evidence(unit_id, version=None, include_pending=False)`

Returns the evidence record document for `unit_id` in the caller's org — the same document
`GET /api/v1/units/{unit_id}/return-evidence` returns for the same org and unit. Returns
`{}` (empty object) when no record exists; per §14.4, a consumer should treat that as
**silent**, not as a negative answer.

- `version`: a specific record version; the latest non-superseded version if omitted.
- `include_pending`: include a minimal pre-finalization document when the return has not
  been finalized yet, instead of returning `{}`.

### `list_return_evidence(since=None, limit=50)`

Returns finalized evidence records for the caller's org — the same records
`GET /api/v1/evidence/export` streams for the same org. `since` is an ISO 8601 UTC
timestamp (inclusive); `limit` is capped at 100.

### `verify_return_chain(unit_id)`

Recomputes and verifies the event chain and evidence-record integrity for `unit_id` in the
caller's org — the same computation behind
`GET /api/v1/units/{unit_id}/chain/verification`. Returns
`{org_id, unit_id, valid, units_checked, events_checked, ledger_entries_checked,
records_checked, anchors_checked, first_hash, last_hash, failures, summary}`.

`valid: true` means the chain hash-links verify, sequence numbers have no gaps, and the
recorded document hashes match. This is **tamper-evident, not tamper-proof**: see ADR-007
for the exact claim wording this project uses and why "immutable" or "blockchain-secured"
would overstate it.

### `explain_return_decision(unit_id, question)`

Answers a natural-language `question` about the decision for `unit_id` using only the
evidence record and event history already on file — it never calls a model and never
proposes a new verdict. Returns `{answer, citations, not_recorded}`.

This is a lightweight, field-summary explainer. The full model-backed Explainer Agent
(§11.14) is planned for P14 and, when built, will replace this tool's implementation
without changing its name or output shape.

## Parity with REST

Every tool delegates to the same service-layer functions the REST routes call
(`contract.service.get_evidence_document`, `contract.service.export_evidence_stream`,
`chain.service.run_verify_unit`) — there is exactly one code path per operation, not a
parallel MCP-specific implementation that could drift from REST. See `test_contract.py`
(T-CON-13) and `test_mcp_server.py` for the tests backing this claim.

## What is intentionally not exposed

- No write tools (create/update/decide/override/sign-off) — those remain REST-only, behind
  the full permission and four-eyes checks in `review/service.py`.
- No tool accepts `org_id`, a signed photo URL, or a thinking/reasoning field.
- `explain_return_decision` never returns model "thinking" content — see `CLAUDE.md`,
  "never request or persist thoughts".
