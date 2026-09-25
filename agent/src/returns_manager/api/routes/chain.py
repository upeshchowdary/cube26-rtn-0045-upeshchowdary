"""GET /api/v1/units/{unit_id}/chain/verification — read-only chain verifier (§13.5)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from returns_manager.api.deps import ServicesDep
from returns_manager.chain.service import run_verify_unit

router = APIRouter(prefix="/api/v1/units", tags=["chain"])


class ChainVerificationResponse(BaseModel):
    org_id: str
    unit_id: str
    valid: bool
    units_checked: int
    events_checked: int
    ledger_entries_checked: int
    records_checked: int
    anchors_checked: int
    first_hash: str | None = None
    last_hash: str | None = None
    failures: list[str] = []
    summary: str


@router.get(
    "/{unit_id}/chain/verification",
    response_model=ChainVerificationResponse,
    summary="Verify the event chain for a unit (§13.5)",
)
async def verify_unit_chain(
    unit_id: str,
    svc: ServicesDep,
    org_id: str = Query(..., description="Org to verify within."),
    anchors_file: str = Query("anchors/ledger-anchors.jsonl", description="Anchors JSONL path."),
) -> ChainVerificationResponse:
    """Recompute every hash and check seq continuity for `unit_id` in `org_id`.

    This is a read-only operation.  It does not modify any data.
    """
    result = await run_verify_unit(svc.db.pool, org_id, unit_id, anchors_file)
    return ChainVerificationResponse(
        org_id=org_id,
        unit_id=unit_id,
        valid=result.valid,
        units_checked=result.units_checked,
        events_checked=result.events_checked,
        ledger_entries_checked=result.ledger_entries_checked,
        records_checked=result.records_checked,
        anchors_checked=result.anchors_checked,
        first_hash=result.first_hash,
        last_hash=result.last_hash,
        failures=result.failures,
        summary=result.summary_line(),
    )
