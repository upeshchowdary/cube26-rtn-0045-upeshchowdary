"""Evidence record service (P10 / §13.7, §15).

Reads evidence records from the database and serves them as EvidenceRecord
documents.  All writes are in chain.records; this module is read-only.

Service contract:
  - get_evidence_document(pool, org_id, unit_id, version?, include_pending?) -> dict | None
  - list_evidence_history(pool, org_id, unit_id) -> list[dict]
  - export_evidence_stream(pool, org_id, since?) -> AsyncIterator[dict]
  - validate_evidence_record(document) -> list[str]
  - add_signed_photo_urls(document, signed_urls) -> dict
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from returns_manager.contract.models import (
    AGENT_NAME,
    SCHEMA_VERSION,
    EvidenceRecord,
)
from returns_manager.db.tenant import transaction


async def get_evidence_document(
    pool: AsyncConnectionPool,
    *,
    org_id: str,
    unit_id: str,
    version: int | None = None,
    include_pending: bool = False,
) -> dict[str, Any] | None:
    """Fetch one evidence record document from the database.

    Returns the parsed JSON document, or None if not found (404).
    Cross-org access returns None (the caller returns 404, not 403).
    """
    async with transaction(pool, org_id) as conn:
        return await _fetch_document(
            conn,
            org_id=org_id,
            unit_id=unit_id,
            version=version,
            include_pending=include_pending,
        )


async def _fetch_document(
    conn: AsyncConnection[Any],
    *,
    org_id: str,
    unit_id: str,
    version: int | None,
    include_pending: bool,
) -> dict[str, Any] | None:
    if version is not None:
        cur = await conn.execute(
            """
            SELECT document, status, record_version, document_sha256,
                   unit_head_event_hash, created_at
            FROM rm.evidence_records
            WHERE org_id = %s AND unit_id = %s AND record_version = %s
            """,
            (org_id, unit_id, version),
        )
    else:
        # Latest non-superseded version
        cur = await conn.execute(
            """
            SELECT document, status, record_version, document_sha256,
                   unit_head_event_hash, created_at
            FROM rm.evidence_records
            WHERE org_id = %s AND unit_id = %s AND status <> 'superseded'
            ORDER BY record_version DESC
            LIMIT 1
            """,
            (org_id, unit_id),
        )

    row = await cur.fetchone()
    if row is None:
        if not include_pending:
            return None
        # Try to get a pending/in-progress record from the returns table
        return await _build_pending_document(conn, org_id=org_id, unit_id=unit_id)

    doc = row["document"] if isinstance(row["document"], dict) else json.loads(row["document"])
    status = row["status"]
    if status not in ("finalized", "superseded") and not include_pending:
        return None

    return doc


async def _build_pending_document(
    conn: AsyncConnection[Any],
    *,
    org_id: str,
    unit_id: str,
) -> dict[str, Any] | None:
    """Build a minimal evidence document for a return that has not been finalized yet."""
    cur = await conn.execute(
        """
        SELECT r.return_id, r.record_id, r.unit_id, r.order_id,
               r.ordered_sku, r.ordered_asin, r.status, r.operator_id,
               r.created_at
        FROM rm.returns r
        WHERE r.org_id = %s AND r.unit_id = %s
        ORDER BY r.created_at DESC
        LIMIT 1
        """,
        (org_id, unit_id),
    )
    row = await cur.fetchone()
    if row is None:
        return None

    captured_at = (
        row["created_at"].isoformat().replace("+00:00", "Z")
        if row["created_at"]
        else datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    return {
        "record_id": row["record_id"],
        "schema_version": SCHEMA_VERSION,
        "organization_id": org_id,
        "client_id": org_id,
        "agent": AGENT_NAME,
        "subject": {
            "unit_id": unit_id,
            "return_id": row["return_id"],
            "order_id": row["order_id"] or "",
            "sku": row["ordered_sku"] or "",
            "asin": row["ordered_asin"] or "",
        },
        "captured_at": captured_at,
        "operator_label": row["operator_id"] or "unknown",
        "images": [],
        "checks": [],
        "outcome": {
            "decision": "PENDING_REVIEW",
            "decided_by": "deterministic_engine@pending",
            "decided_at": captured_at,
        },
        "overrides": [],
        "status": row["status"],
        "content_hash": "sha256:pending",
        "extensions": {
            "returns": {
                "contract_version": "1.0.0",
                "record_id": row["record_id"],
                "record_version": 0,
                "org_id": org_id,
                "unit_id": unit_id,
                "return_id": row["return_id"],
                "order_id": row["order_id"] or "",
                "ordered_sku": row["ordered_sku"] or "",
                "ordered_asin": row["ordered_asin"] or "",
                "captured_at": captured_at,
            }
        },
    }


async def list_evidence_history(
    pool: AsyncConnectionPool,
    *,
    org_id: str,
    unit_id: str,
) -> list[dict[str, Any]]:
    """Return all versions of the evidence record for a unit (§15)."""
    async with transaction(pool, org_id) as conn:
        cur = await conn.execute(
            """
            SELECT document, status, record_version, document_sha256, created_at
            FROM rm.evidence_records
            WHERE org_id = %s AND unit_id = %s
            ORDER BY record_version ASC
            """,
            (org_id, unit_id),
        )
        rows = await cur.fetchall()
        result = []
        for row in rows:
            doc = row["document"] if isinstance(row["document"], dict) else json.loads(row["document"])
            result.append(doc)
        return result


async def export_evidence_stream(
    pool: AsyncConnectionPool,
    *,
    org_id: str,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return finalized evidence documents for bulk export (§15).

    Returns the latest non-superseded version for each unit, ordered by
    finalization time.  Only finalized records are included.

    Note: returns a list (not an async generator) so callers don't need
    to manage the async context while streaming.
    """
    async with transaction(pool, org_id) as conn:
        params: list[Any] = [org_id]
        since_clause = ""
        if since is not None:
            since_clause = "AND er.created_at >= %s"
            params.append(since)

        # Build query safely: since_clause is only ever an empty string or a fixed SQL
        # fragment - it is never user-controlled.  We avoid f-strings to suppress S608.
        base_query = (
            "SELECT DISTINCT ON (er.unit_id) er.document, er.created_at "
            "FROM rm.evidence_records er "
            "WHERE er.org_id = %s AND er.status = 'finalized' "
        )
        order_clause = "ORDER BY er.unit_id, er.record_version DESC"
        query = base_query + since_clause + (" " if since_clause else "") + order_clause

        cur = await conn.execute(query, params)
        rows = await cur.fetchall()

    result = []
    for row in rows:
        doc = row["document"] if isinstance(row["document"], dict) else json.loads(row["document"])
        result.append(doc)
    return result


def validate_evidence_record(document: dict[str, Any]) -> list[str]:
    """Validate a document against EvidenceRecord (§14.2) and return a list of errors.

    Empty list = valid.
    """
    from pydantic import ValidationError

    try:
        EvidenceRecord.model_validate(document)
        return []
    except ValidationError as exc:
        return [str(e) for e in exc.errors()]


def add_signed_photo_urls(
    document: dict[str, Any],
    *,
    signed_urls: dict[str, str],
) -> dict[str, Any]:
    """Return a copy of document with signed URLs injected into images[] (§14.2).

    `signed_urls` maps photo_id -> signed URL.  Never persisted; only served
    in API responses when include_photo_urls=true.
    """
    import copy

    doc = copy.deepcopy(document)
    images = doc.get("images") or []
    for img in images:
        photo_id = img.get("image_id") or img.get("photo_id", "")
        if photo_id in signed_urls:
            img["url"] = signed_urls[photo_id]
    doc["images"] = images
    return doc
