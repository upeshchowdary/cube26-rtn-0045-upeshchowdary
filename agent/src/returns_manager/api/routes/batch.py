"""Batch-upload jobs API (§15): upload a before/returned CSV pair, run the real standalone
batch pipeline against it, poll status, read the resulting rows, download the output CSV,
or delete the job and its files. See `batch/jobs_service.py` for what a "job" is here and
why it deliberately isn't the durable DB job queue used elsewhere.

Every route is scoped to the caller's own org via the authenticated `Principal`, same as
every other route in this API - a batch job lives at `<root>/<org_id>/<job_id>/` and one
org can never see, download or delete another org's upload.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Response, UploadFile
from pydantic import BaseModel, Field

from returns_manager.api.deps import PrincipalDep, ServicesDep
from returns_manager.batch.jobs_service import BatchJob
from returns_manager.disposition.engine import Route
from returns_manager.errors import BadRequest, NotFound
from returns_manager.security.roles import Permission, require

router = APIRouter(prefix="/api/v1/batch", tags=["batch"])

# A CSV here is a handful of return records, not a bulk data export - this is a demo/import
# size guard, not a real-world bulk-upload limit.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
# Spend guard default (CLAUDE.md "Spend guards"): a caller must explicitly raise this to
# spend more than a small number of real Gemini requests in one job.
DEFAULT_MAX_REQUESTS = 15
MAX_MAX_REQUESTS = 50


class BatchJobResponse(BaseModel):
    job_id: str
    org_id: str
    status: str
    created_at: float
    before_filename: str
    returned_filename: str
    total_rows: int
    processed: int
    uncertain: int
    live_requests: int
    error: str | None
    notes: list[str]


def _to_response(job: BatchJob) -> BatchJobResponse:
    return BatchJobResponse(
        job_id=job.job_id,
        org_id=job.org_id,
        status=job.status,
        created_at=job.created_at,
        before_filename=job.before_filename,
        returned_filename=job.returned_filename,
        total_rows=job.total_rows,
        processed=job.processed,
        uncertain=job.uncertain,
        live_requests=job.live_requests,
        error=job.error,
        notes=job.notes,
    )


def _split_combined_csv(content: bytes, default_org_id: str) -> tuple[bytes, bytes]:
    import csv
    import io

    text = content.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    rows = list(reader)
    if not rows:
        raise BadRequest("uploaded CSV has no data rows")

    has_sold = any(k.startswith("sold_") for k in fieldnames)
    has_returned = any(k.startswith("returned_") for k in fieldnames)

    if has_sold or has_returned:
        b_out = io.StringIO()
        r_out = io.StringIO()
        bw = csv.DictWriter(
            b_out,
            fieldnames=[
                "record_id",
                "unit_id",
                "org_id",
                "order_id",
                "ordered_sku",
                "ordered_asin",
                "identity_match",
                "parts_list",
                "time",
                "photo_ref",
                "category",
            ],
        )
        rw = csv.DictWriter(
            r_out,
            fieldnames=[
                "record_id",
                "unit_id",
                "org_id",
                "order_id",
                "ordered_sku",
                "ordered_asin",
                "returned_photo_ref",
                "time",
            ],
        )
        bw.writeheader()
        rw.writeheader()

        for idx, r in enumerate(rows, 1):
            unit_id = (r.get("unit_id") or f"UNIT-{idx}").strip()
            bw.writerow(
                {
                    "record_id": (r.get("sold_record_id") or r.get("record_id") or f"REC-SOLD-{idx}").strip(),
                    "unit_id": unit_id,
                    "org_id": (r.get("sold_org_id") or r.get("org_id") or default_org_id).strip(),
                    "order_id": (r.get("sold_order_id") or r.get("order_id") or f"ORD-{idx}").strip(),
                    "ordered_sku": (r.get("sold_sku") or r.get("ordered_sku") or "SKU-DEFAULT").strip(),
                    "ordered_asin": (r.get("sold_asin") or r.get("ordered_asin") or "B0DEFAULT").strip(),
                    "identity_match": (r.get("identity_match") or "uncertain").strip(),
                    "parts_list": (r.get("parts_list") or "").strip(),
                    "time": (r.get("sold_time") or r.get("time") or "2026-08-01T00:00:00Z").strip(),
                    "photo_ref": (r.get("sold_photo_url") or r.get("photo_ref") or "").strip(),
                    "category": (r.get("category") or "").strip(),
                }
            )
            rw.writerow(
                {
                    "record_id": (
                        r.get("returned_record_id") or r.get("record_id") or f"REC-RTN-{idx}"
                    ).strip(),
                    "unit_id": unit_id,
                    "org_id": (r.get("returned_org_id") or r.get("org_id") or default_org_id).strip(),
                    "order_id": (r.get("returned_order_id") or r.get("order_id") or f"ORD-{idx}").strip(),
                    "ordered_sku": (r.get("returned_sku") or r.get("ordered_sku") or "SKU-DEFAULT").strip(),
                    "ordered_asin": (r.get("returned_asin") or r.get("ordered_asin") or "B0DEFAULT").strip(),
                    "returned_photo_ref": (
                        r.get("returned_photo_url") or r.get("returned_photo_ref") or ""
                    ).strip(),
                    "time": (r.get("returned_time") or r.get("time") or "2026-09-01T00:00:00Z").strip(),
                }
            )

        return b_out.getvalue().encode("utf-8"), r_out.getvalue().encode("utf-8")
    return content, content


@router.post("/jobs", response_model=BatchJobResponse, status_code=202)
async def create_batch_job(
    principal: PrincipalDep,
    svc: ServicesDep,
    confirm_spend: Annotated[bool, Form()],
    file: Annotated[
        UploadFile | None, File(description="Single combined CSV (unit_id,sold_*,returned_*)")
    ] = None,
    before: Annotated[
        UploadFile | None, File(description="Before-sale CSV (record_id,unit_id,org_id,...)")
    ] = None,
    returned: Annotated[
        UploadFile | None, File(description="Returned-item CSV (record_id,unit_id,org_id,...)")
    ] = None,
    default_category: Annotated[str | None, Form()] = None,
    max_requests: Annotated[int, Form(ge=1, le=MAX_MAX_REQUESTS)] = DEFAULT_MAX_REQUESTS,
) -> BatchJobResponse:
    """202 Accepted: the job runs in the background (real Gemini calls). Poll
    GET /jobs/{job_id} for status.

    Accepts either:
    1. A single unified returns CSV (via `file` or `before`) containing sold & returned records
       (e.g. returns_input_30.csv).
    2. A pair of `before` and `returned` CSV files.
    """
    require(principal, Permission.RETURNS_WRITE)
    if svc.batch_jobs is None:
        raise BadRequest("batch processing is not configured on this deployment (no Gemini API key set)")
    if not confirm_spend:
        raise BadRequest("confirm_spend must be true - this run spends real Gemini API quota")

    upload_file = file or (before if returned is None else None)
    if upload_file is not None:
        # Single unified CSV mode
        content = await upload_file.read()
        if not content:
            raise BadRequest("uploaded file is empty")
        if len(content) > MAX_UPLOAD_BYTES:
            raise BadRequest(f"file must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        before_bytes, returned_bytes = _split_combined_csv(content, default_org_id=principal.org_id)
        before_fn = upload_file.filename or "returns.csv"
        returned_fn = upload_file.filename or "returns.csv"
    elif before is not None and returned is not None:
        # Two-file mode
        before_bytes = await before.read()
        returned_bytes = await returned.read()
        if not before_bytes or not returned_bytes:
            raise BadRequest("both a before CSV and a returned CSV are required")
        if len(before_bytes) > MAX_UPLOAD_BYTES or len(returned_bytes) > MAX_UPLOAD_BYTES:
            raise BadRequest(f"each file must be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        before_fn = before.filename or "before.csv"
        returned_fn = returned.filename or "returned.csv"
    else:
        raise BadRequest(
            "either a single unified returns CSV or both before and returned CSV files are required"
        )

    job = await svc.batch_jobs.create_job(
        org_id=principal.org_id,
        before_bytes=before_bytes,
        before_filename=before_fn,
        returned_bytes=returned_bytes,
        returned_filename=returned_fn,
        default_category=default_category,
        max_requests=max_requests,
        created_by=principal.actor_label,
    )
    return _to_response(job)


@router.get("/jobs", response_model=list[BatchJobResponse])
async def list_batch_jobs(principal: PrincipalDep, svc: ServicesDep) -> list[BatchJobResponse]:
    require(principal, Permission.RETURNS_READ)
    if svc.batch_jobs is None:
        return []
    return [_to_response(job) for job in svc.batch_jobs.list_jobs(principal.org_id)]


@router.post("/cache/clear")
async def clear_batch_cache(principal: PrincipalDep, svc: ServicesDep) -> dict[str, int]:
    """Clears all stored batch job cache files and records for this organization."""
    require(principal, Permission.RETURNS_WRITE)
    if svc.batch_jobs is None:
        return {"cleared": 0}
    count = svc.batch_jobs.clear_all_jobs(principal.org_id)
    return {"cleared": count}


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_batch_job(job_id: str, principal: PrincipalDep, svc: ServicesDep) -> None:
    require(principal, Permission.RETURNS_WRITE)
    if svc.batch_jobs is None or not svc.batch_jobs.delete_job(principal.org_id, job_id):
        raise NotFound(f"no batch job {job_id!r}")


@router.get("/jobs/{job_id}", response_model=BatchJobResponse)
async def get_batch_job(job_id: str, principal: PrincipalDep, svc: ServicesDep) -> BatchJobResponse:
    require(principal, Permission.RETURNS_READ)
    job = svc.batch_jobs.get_job(principal.org_id, job_id) if svc.batch_jobs else None
    if job is None:
        raise NotFound(f"no batch job {job_id!r}")
    return _to_response(job)


@router.get("/jobs/{job_id}/rows")
async def get_batch_job_rows(job_id: str, principal: PrincipalDep, svc: ServicesDep) -> list[dict[str, str]]:
    """The evidence rows this job produced - the same data `output.csv` holds, as JSON so
    the dashboard can render it directly without parsing a CSV client-side."""
    require(principal, Permission.RETURNS_READ)
    rows = svc.batch_jobs.output_rows(principal.org_id, job_id) if svc.batch_jobs else None
    if rows is None:
        return []
    return rows


@router.get("/jobs/{job_id}/output.csv")
async def download_batch_job_output(job_id: str, principal: PrincipalDep, svc: ServicesDep) -> Response:
    """Renders the output CSV fresh on every request, with `operator_disposition` reflecting the
    latest recorded `override` decision on top of the engine's own route (see
    `BatchJobsService.render_output_csv`) - what a reviewer downloads matches what they approved
    in the UI, not a stale snapshot from the moment the job finished."""
    require(principal, Permission.RETURNS_READ)
    csv_bytes = svc.batch_jobs.render_output_csv(principal.org_id, job_id) if svc.batch_jobs else None
    if csv_bytes is None:
        raise NotFound(f"no completed output for batch job {job_id!r} (it may still be processing)")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="returns_output_{job_id}.csv"'},
    )


@router.get("/jobs/{job_id}/rows/{record_id}/detail")
async def get_batch_job_row_detail(
    job_id: str, record_id: str, principal: PrincipalDep, svc: ServicesDep
) -> dict[str, Any]:
    """The rich per-row detail (§14.2 fixed check list, fused identity/completeness/condition,
    disposition reasoning, raw model output) for one row - everything `output.csv`'s flat columns
    leave out. 404 for a row that hasn't finished, doesn't exist, or fell back to fail-open (there
    is no real pipeline run to show for that row)."""
    require(principal, Permission.RETURNS_READ)
    detail = svc.batch_jobs.output_row_detail(principal.org_id, job_id, record_id) if svc.batch_jobs else None
    if detail is None:
        raise NotFound(f"no detail for batch job {job_id!r} row {record_id!r}")
    return detail


class RowDecisionRequest(BaseModel):
    action: Literal["accept", "override", "retake_request", "review_request"]
    # Only the four dispositions (§12.2); any other value is rejected with 422.
    new_disposition: Route | None = None
    reason: str = Field(..., min_length=1, max_length=2000)


class RowDecisionEntry(BaseModel):
    record_id: str
    action: str
    new_disposition: str | None
    reason: str
    actor: str
    at: float


@router.post("/jobs/{job_id}/rows/{record_id}/decision", response_model=RowDecisionEntry, status_code=201)
async def record_batch_row_decision(
    job_id: str,
    record_id: str,
    body: RowDecisionRequest,
    principal: PrincipalDep,
    svc: ServicesDep,
) -> RowDecisionEntry:
    """Records one operator/reviewer decision against a row - accept, override (needs
    `review:write`, like overriding a DB-backed disposition does), or a retake/review request.
    Appended, never overwriting an earlier decision; the full history is always readable via
    GET .../decisions. The downloaded output CSV picks up an `override`'s `new_disposition`."""
    require(principal, Permission.RETURNS_WRITE)
    if body.action == "override":
        require(principal, Permission.REVIEW_WRITE)
        if not body.new_disposition:
            raise BadRequest("override requires new_disposition")
    if svc.batch_jobs is None:
        raise BadRequest("batch processing is not configured on this deployment (no Gemini API key set)")
    if body.action in ("accept", "override") and svc.batch_jobs.row_requires_signoff(
        principal.org_id, job_id, record_id
    ):
        require(principal, Permission.SIGNOFF)  # S01 dispose / S02 high value (§12.2)
    entry = svc.batch_jobs.record_decision(
        principal.org_id,
        job_id,
        record_id,
        action=body.action,
        new_disposition=body.new_disposition,
        reason=body.reason,
        actor=principal.actor_label,
    )
    if entry is None:
        raise NotFound(f"no batch job {job_id!r}")
    return RowDecisionEntry.model_validate(entry)


@router.get("/jobs/{job_id}/rows/{record_id}/decisions", response_model=list[RowDecisionEntry])
async def list_batch_row_decisions(
    job_id: str, record_id: str, principal: PrincipalDep, svc: ServicesDep
) -> list[RowDecisionEntry]:
    require(principal, Permission.RETURNS_READ)
    decisions = svc.batch_jobs.get_decisions(principal.org_id, job_id, record_id) if svc.batch_jobs else None
    if decisions is None:
        raise NotFound(f"no batch job {job_id!r}")
    return [RowDecisionEntry.model_validate(d) for d in decisions]
