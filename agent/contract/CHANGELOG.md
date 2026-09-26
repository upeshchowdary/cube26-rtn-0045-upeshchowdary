# Contract changelog

Format: [semver] date — change. Follows the versioning policy in ADR-005 and §14.6.

## [1.0.0] — 2026-09-25

Initial cross-pod evidence contract (Phase 10).

- Fixed evidence-record contract (§14.2): `record_id`, `schema_version`, `organization_id`,
  `client_id`, `agent`, `subject`, `captured_at`, `operator_label`, `images`, `checks`,
  `outcome`, `overrides`, `status`, `content_hash`.
- `extensions.returns` block (§14.2b) carrying all Returns-specific detail.
- Flat view (§14.3): 15 official columns (matching `data/returns_sample.csv` byte for
  byte) plus 14 Returns-specific additions.
- REST evidence endpoints: `GET /api/v1/units/{unit_id}/return-evidence`,
  `GET /api/v1/units/{unit_id}/return-evidence/history`,
  `GET /api/v1/evidence/export`.
- Read-only MCP server (§16) with 4 tools: `get_return_evidence`, `list_return_evidence`,
  `verify_return_chain`, `explain_return_decision`.
- `openapi.json` export.

### Fixed after initial P10 re-verification (2026-09-26)

The following were found and corrected during a post-merge re-check, before any external
consumer depended on this version — no contract shape changed, so this is not a new
version, only a correction to the implementation:

- **MCP authentication.** The four MCP tools originally accepted `org_id` as a plain
  caller-supplied argument with no authentication check, letting any MCP client read any
  organization's evidence. They now authenticate every request with the same API-key
  mechanism REST uses (`Authorization: Bearer rmk_<env>_...`) and derive `org_id`
  exclusively from the verified key; no tool accepts `org_id` as an argument any more.
- **MCP SDK API.** The installed `mcp` package's v2 API renamed `FastMCP` to `MCPServer`
  and changed `run_async` to `run_streamable_http_async`; `mcp_server.py` was updated to
  the current API (it previously would not import).
- **`contract/service.py` read path.** `get_evidence_document`, `list_evidence_history`,
  and `export_evidence_stream` selected a column named `created_at` on
  `rm.evidence_records`, which does not exist — the writer (`chain/records.py`) has always
  used `finalized_at`. Every read of a real finalized record raised `UndefinedColumn`, live,
  the first time either REST or MCP was exercised against a real database row (rather than
  the hand-built, never-persisted documents the original unit tests used). Fixed to select
  `finalized_at`; regression tests `T-CON-17`/`T-CON-18` now round-trip a real inserted
  record through both functions.
- **Windows event loop.** `returns-manager mcp serve` called `asyncio.run(...)` directly,
  which uses the default `ProactorEventLoop` on Windows — a loop psycopg's async mode
  cannot use. It now uses the project's existing `db.pool.run_async` helper, matching
  every other CLI command.
- Generated artifacts (`evidence-record.v1.schema.json`, `return-evidence-flat.v1.schema.json`,
  `flat-columns.v1.csv`, `openapi.json`) were committed to this directory; they had been
  built once locally by `contract build` but never written to the repository.

## Unreleased

- Nothing pending.
