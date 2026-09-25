"""Read-only MCP server for cross-pod agent access (§16).

Served as its own process: returns-manager mcp serve
Authenticated by API key with scope evidence:read.
The key's org scopes every call.

Tools (annotated read-only):
  - get_return_evidence(unit_id, version?, include_pending?)
  - list_return_evidence(since, limit, cursor?)
  - verify_return_chain(unit_id)
  - explain_return_decision(unit_id, question)

Tool output is the same Pydantic models as REST (byte-identical after JCS).
No write tools. Least privilege for agent-to-agent traffic.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _build_mcp_server(settings_override: Any = None) -> Any:
    """Build and return the FastMCP server instance.

    Import is deferred so that the MCP package is only required when this
    entry point is actually invoked (not at import time of the whole package).
    """
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "The 'mcp' package is required for the MCP server. Install it with: uv add mcp"
        ) from exc

    from returns_manager.config import get_settings
    from returns_manager.db.pool import Database

    settings = settings_override or get_settings()
    settings.require("database_url")
    assert settings.database_url is not None

    mcp: FastMCP = FastMCP(
        name="returns-manager",
        description=(
            "Read-only MCP server for Returns Manager evidence records. "
            "Every call is scoped to the org associated with the API key used to authenticate."
        ),
    )

    # Build a minimal DB pool for each request.
    # In the MCP server we use a single shared pool (opened at startup).
    _db = Database(settings.database_url.get_secret_value())

    # ── Tool: get_return_evidence ─────────────────────────────────────────────

    @mcp.tool(description="Get the evidence record for a unit_id.")  # type: ignore[untyped-decorator]
    async def get_return_evidence(
        unit_id: str,
        org_id: str,
        version: int | None = None,
        include_pending: bool = False,
    ) -> dict[str, Any]:
        """Return the evidence record document for unit_id in the given org.

        Returns the latest non-superseded version unless version is specified.
        Returns an empty dict {} when no record exists (the caller should treat
        this as 'silent' per §14.4).
        """
        from returns_manager.contract.service import get_evidence_document

        await _db.open()
        doc = await get_evidence_document(
            _db.pool,
            org_id=org_id,
            unit_id=unit_id,
            version=version,
            include_pending=include_pending,
        )
        return doc if doc is not None else {}

    # ── Tool: list_return_evidence ────────────────────────────────────────────

    @mcp.tool(description="List evidence records for an org, optionally filtered by timestamp.")  # type: ignore[untyped-decorator]
    async def list_return_evidence(
        org_id: str,
        since: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return finalized evidence records for the org.

        `since` is an ISO 8601 UTC timestamp (inclusive).
        `limit` caps the number of results (max 100).
        """
        from datetime import datetime

        from returns_manager.contract.service import export_evidence_stream

        since_dt: datetime | None = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                since_dt = None

        await _db.open()
        records = await export_evidence_stream(
            _db.pool,
            org_id=org_id,
            since=since_dt,
        )
        capped = min(max(1, limit), 100)
        return records[:capped]

    # ── Tool: verify_return_chain ─────────────────────────────────────────────

    @mcp.tool(description="Verify the event chain integrity for a unit.")  # type: ignore[untyped-decorator]
    async def verify_return_chain(
        unit_id: str,
        org_id: str,
    ) -> dict[str, Any]:
        """Recompute and verify the event chain for unit_id.

        Returns a verification summary dict with 'valid: bool' and 'summary' string.
        """
        from returns_manager.chain.service import run_verify_unit

        await _db.open()
        result = await run_verify_unit(
            _db.pool,
            org_id,
            unit_id,
            "anchors/ledger-anchors.jsonl",
        )
        return {
            "org_id": org_id,
            "unit_id": unit_id,
            "valid": result.valid,
            "units_checked": result.units_checked,
            "events_checked": result.events_checked,
            "ledger_entries_checked": result.ledger_entries_checked,
            "records_checked": result.records_checked,
            "anchors_checked": result.anchors_checked,
            "first_hash": result.first_hash,
            "last_hash": result.last_hash,
            "failures": result.failures,
            "summary": result.summary_line(),
        }

    # ── Tool: explain_return_decision ─────────────────────────────────────────

    @mcp.tool(  # type: ignore[untyped-decorator]
        description=(
            "Answer a natural-language question about why a return decision was made. "
            "Read-only; never proposes new verdicts."
        )
    )
    async def explain_return_decision(
        unit_id: str,
        org_id: str,
        question: str,
    ) -> dict[str, Any]:
        """Answer `question` about the decision for unit_id using the evidence record.

        Returns {answer, citations, not_recorded}.
        This is a lightweight explainer that reads from the evidence record and events.
        The full Explainer Agent (§11.14) is planned for P14.
        """
        await _db.open()

        from returns_manager.contract.service import get_evidence_document

        doc = await get_evidence_document(
            _db.pool,
            org_id=org_id,
            unit_id=unit_id,
            include_pending=True,
        )
        if doc is None:
            return {
                "answer": "No evidence record found for this unit.",
                "citations": [],
                "not_recorded": [question],
            }

        # Build a concise summary from the evidence record fields
        ext = doc.get("extensions", {}).get("returns", {})
        if hasattr(ext, "model_dump"):
            ext = ext.model_dump()

        checks_summary = "; ".join(
            f"{c.get('check_key', '?')}={c.get('verdict', '?')}" for c in (doc.get("checks") or [])
        )
        outcome = doc.get("outcome", {})

        answer = (
            f"Decision for {unit_id}: {outcome.get('decision', 'unknown')} "
            f"(decided by {outcome.get('decided_by', 'unknown')} at {outcome.get('decided_at', 'unknown')}). "
            f"Checks: {checks_summary or 'none recorded'}. "
            f"Status: {doc.get('status', 'unknown')}."
        )

        citations = [
            {"kind": "record_field", "ref": f"outcome.decision={outcome.get('decision')}"},
            {"kind": "record_field", "ref": f"status={doc.get('status')}"},
        ]

        return {
            "answer": answer,
            "citations": citations,
            "not_recorded": [],
        }

    return mcp


def run_mcp_server(host: str = "0.0.0.0", port: int = 8001) -> None:  # noqa: S104
    """Entry point for `returns-manager mcp serve`."""
    import asyncio

    mcp = _build_mcp_server()
    logger.info("Starting MCP server on %s:%d", host, port)
    asyncio.get_event_loop().run_until_complete(
        mcp.run_async(transport="streamable-http", host=host, port=port)
    )
