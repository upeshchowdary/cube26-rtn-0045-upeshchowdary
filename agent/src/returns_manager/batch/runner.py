"""Orchestrates one batch run: join before/returned rows, download photos, run the real
judgment session + deterministic pipeline per return, write one output CSV row each.

No database, no job queue. Every row fails open: a download error, a missing before-
record, an unmapped category or a model/provider failure never crashes the run and never
guesses a verdict - that row is written as `observed_state=uncertain`,
`operator_disposition=pending_review` with the reason logged, and the run continues.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import logging

import httpx
import yaml

from returns_manager.batch.cards import VALID_CATEGORIES, build_card
from returns_manager.batch.images import ImageFetchError, fetch_image
from returns_manager.batch.io_csv import BeforeRow, ReturnedRow, read_before_csv, read_returned_csv
from returns_manager.batch.parts import parse_parts_list
from returns_manager.canonical.hashing import sha256_hex
from returns_manager.config import REPO_ROOT, Settings
from returns_manager.jobs.budget import TokenBucketRateLimiter
from returns_manager.jobs.retry import classify_error
from returns_manager.judgment.pipeline import PhotoGate, run_pipeline
from returns_manager.judgment.types import EffectivePolicy
from returns_manager.llm.client import ModelClient
from returns_manager.llm.context import ContextBundle, ReturnPhoto, assemble
from returns_manager.llm.loop import SessionFailed, run_session
from returns_manager.reference.models import CategoryPolicyV1, ConditionRubricV1

RETRYABLE_ATTEMPTS = 2  # this row's own retry budget for transient provider errors (§10.4 "retry" action)
RETRY_DELAY_S = 5.0

REF_DIR = REPO_ROOT / "reference"

logger = logging.getLogger(__name__)


def load_rubric(category_key: str) -> ConditionRubricV1:
    active = yaml.safe_load((REF_DIR / "rubrics" / "active.yaml").read_text(encoding="utf-8"))
    snapshot_id = active["active_snapshots"].get(category_key)
    if not snapshot_id:
        raise ValueError(f"no active rubric snapshot configured for category {category_key!r}")
    for path in sorted((REF_DIR / "rubrics").rglob("*.yaml")):
        if path.name == "active.yaml":
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if doc.get("snapshot_id") == snapshot_id:
            return ConditionRubricV1.model_validate(doc)
    raise ValueError(f"no rubric file matches active snapshot {snapshot_id!r}")


def load_policy(category_key: str) -> EffectivePolicy:
    path = REF_DIR / "policies" / "amazon.co.uk" / f"{category_key}.yaml"
    if not path.is_file():
        raise ValueError(f"no policy file for category {category_key!r} ({path})")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return EffectivePolicy.from_policy(CategoryPolicyV1.model_validate(doc))


@dataclass
class _NoDbReservation:
    limiter: TokenBucketRateLimiter

    async def take(self) -> None:
        await self.limiter.acquire(timeout_s=120)


class _NoDbQuota:
    """Same shape as llm.quota.QuotaGuard, without a database - this run is standalone.

    There is no daily-budget ledger here; `--max-requests` on the CLI is this run's own
    spend guard instead. It still throttles requests per minute per model with the same
    `TokenBucketRateLimiter` the real QuotaGuard uses - one instance shared across the whole
    run (never per-row: a fresh limiter every row would never actually pace anything), so a
    batch of many rows on a fresh key does not immediately trip Gemini's own per-minute
    rate limit the way an unthrottled loop does.
    """

    def __init__(self, rpm: float) -> None:
        self._rpm = rpm
        self._limiters: dict[str, TokenBucketRateLimiter] = {}
        self.is_exhausted: bool = False

    def _limiter(self, model_id: str) -> TokenBucketRateLimiter:
        if model_id not in self._limiters:
            limiter = TokenBucketRateLimiter(self._rpm)
            limiter.tokens = 0.0
            self._limiters[model_id] = limiter
        return self._limiters[model_id]

    @asynccontextmanager
    async def reserve(self, model_id: str, role: str, n: int) -> AsyncIterator[_NoDbReservation]:
        if self.is_exhausted:
            from returns_manager.errors import QuotaExhaustedError
            raise QuotaExhaustedError("daily request quota used up")
        yield _NoDbReservation(self._limiter(model_id))

    async def mark_exhausted(self, model_id: str, role: str) -> None:
        self.is_exhausted = True


@dataclass
class RowResult:
    output_row: dict[str, str]
    note: str | None  # None on a clean success; otherwise why the row is a fail-open uncertain
    attempted_model_call: bool  # True iff a live request actually left this machine for this row
    warning: str | None = None  # non-fatal issue on an otherwise-successful row (e.g. one of
    # several photo URLs failed but enough others fetched to still judge the return)
    detail: dict[str, Any] | None = None  # the rich per-row detail (§14.2 checks, identity,
    # completeness, condition, claims, decision, validator actions, raw judgment) - only ever set
    # on a genuine successful pipeline run (`note is None`); a fail-open/uncertain row has nothing
    # real to show beyond `output_row` and `note`, so it stays None rather than showing a guess.


def _build_row_detail(
    *,
    session_judgment: Any,
    result: Any,
    row: ReturnedRow,
    before: BeforeRow,
) -> dict[str, Any]:
    """Everything `process_returned_row` already computes in memory but the flat CSV row
    discards - the exact §14.2 fixed check list, the fused/gated deterministic results, and the
    raw model output - assembled as a plain JSON-serializable dict for the UI's inspection detail
    view. Built field-by-field (never `dataclasses.asdict(result)` on the whole `PipelineResult`)
    because `result.judgment` is a pydantic `JudgmentV1`, not a dataclass; `asdict()` would leave a
    live pydantic instance sitting in the tree instead of raising, and `json.dumps` would only fail
    on it later, further from the cause.

    Only ever built from a real model response plus the deterministic pipeline: nothing here is
    inferred from filenames, URLs, IDs or free-text columns, and nothing overrides the engine.
    """
    return {
        "judgment": result.judgment.model_dump(mode="json"),
        "judgment_raw": session_judgment.model_dump(mode="json"),
        "validator_actions": [asdict(a) for a in result.report.actions],
        "checks": [asdict(c) for c in result.checks],
        "presence": asdict(result.presence),
        "identity": asdict(result.identity),
        "completeness": asdict(result.completeness),
        "condition": asdict(result.condition),
        "claims": asdict(result.claims),
        "decision": asdict(result.decision),
        "escalation_triggers": list(result.escalation_triggers),
        "requires_review": result.requires_review,
        "review_reasons": list(result.review_reasons),
        "returned_photo_refs": list(row.returned_photo_refs),
        "reference_photo_ref": before.photo_ref,
    }


@dataclass
class BatchSummary:
    total_rows: int = 0
    processed: int = 0
    uncertain: int = 0
    live_requests: int = 0
    notes: list[str] = field(default_factory=list)


def check_id_match(before: BeforeRow | None, row: ReturnedRow) -> str:
    """Do the IDs on the *returned* record actually match the IDs recorded when this same
    unit was *sold*? This is a plain data check, independent of anything a photo shows -
    a returned package can carry the wrong order number or SKU on its label even when the
    photo inside it is completely genuine, and a photo-based identity match can't catch
    that. Compares every id the two records both carry; any disagreement is reported, not
    just the first one found, so a human reviewing this doesn't have to re-check by hand.
    """
    if before is None:
        return "NOT MATCHED: no sold-record for this unit_id"
    mismatches = []
    if before.org_id != row.org_id:
        mismatches.append(f"org_id: sold={before.org_id!r} vs returned={row.org_id!r}")
    if before.order_id != row.order_id:
        mismatches.append(f"order_id: sold={before.order_id!r} vs returned={row.order_id!r}")
    if before.ordered_sku != row.ordered_sku:
        mismatches.append(f"ordered_sku: sold={before.ordered_sku!r} vs returned={row.ordered_sku!r}")
    if before.ordered_asin != row.ordered_asin:
        mismatches.append(f"ordered_asin: sold={before.ordered_asin!r} vs returned={row.ordered_asin!r}")
    if mismatches:
        return "NOT MATCHED: " + "; ".join(mismatches)
    return "matched"


def _disposition_for_id_check(before: BeforeRow | None, id_check: str, fallback: str) -> str:
    """A returned unit whose sold-record IDs don't match is flagged wrong_product
    regardless of what the photo-based pipeline concluded - mismatched paperwork on the
    returned package is a stronger, independent signal than condition grading, and a
    correct-looking photo can't excuse it. Not applied when there is no sold record at
    all to compare against (that's a missing-data problem, not a proven mismatch)."""
    if before is not None and id_check.startswith("NOT MATCHED"):
        return "wrong_product"
    return fallback


def _uncertain_row(row: ReturnedRow, before: BeforeRow | None, reason: str) -> dict[str, str]:
    """The fail-open row (§3): no verdict, no grade, no confidence - just the reason. Written for
    every row that did not get a real model response run through the deterministic pipeline."""
    id_check = check_id_match(before, row)
    return {
        "record_id": row.record_id,
        "unit_id": row.unit_id,
        "org_id": row.org_id,
        "order_id": row.order_id,
        "ordered_sku": row.ordered_sku,
        "ordered_asin": row.ordered_asin,
        "identity_match": before.identity_match if before else "uncertain",
        "photo_identity_match": "uncertain",  # no model verdict on the returned photo this run
        "parts_list": before.parts_list if before else "",
        "parts_missing": "",
        "observed_state": "uncertain",
        "amazon_condition": "uncertain",
        "operator_disposition": _disposition_for_id_check(before, id_check, "pending_review"),
        "photo_refs": ";".join(row.returned_photo_refs),
        "captured_at": row.time,
        "sold_vs_returned_id_check": id_check,
        "failure_reason": reason,
    }


def _missing_parts_field(pipeline_completeness: Any) -> str:
    """The sample schema has one column for "missing"; a confirmed-missing part and an
    uncertain one are both reported here (matches the sample's own RTN-0092 precedent,
    where observed_state=uncertain and parts_missing both carry the affected part)."""
    names = [n for n in pipeline_completeness.parts_missing.split(";") if n]
    for n in pipeline_completeness.parts_uncertain.split(";"):
        if n and n not in names:
            names.append(n)
    return ";".join(names)


async def _run_judgment_with_fallback(
    client: ModelClient, bundle: ContextBundle, settings: Settings, quota: _NoDbQuota
) -> Any:
    """Same §10.4a fallback as inspection.service.JudgmentHandler, plus this row's own bounded
    retry for transient provider errors (there is no persistent job queue here to retry the
    row later, so this standalone tool does it inline instead):

    - `quota_exhausted` on the primary model -> one fresh session on RM_JUDGMENT_FALLBACK_MODEL
      (never a mid-session model switch; the fallback is an entirely new session).
    - A transient, §10.4-retryable error (server_error, rate_limit, timeout, network) -> up to
      RETRYABLE_ATTEMPTS attempts on the same model, with a short delay between them.
    - Anything else (safety_blocked, invalid_request, auth, schema_error, ...) -> raised
      immediately; retrying would not change the outcome.
    """
    last: SessionFailed | None = None
    for attempt in range(RETRYABLE_ATTEMPTS):
        try:
            return await run_session(client, quota, bundle, settings)  # type: ignore[arg-type]
        except SessionFailed as failed:
            last = failed
            fallback_model = settings.rm_judgment_fallback_model
            if (
                getattr(failed.cause, "error_class", None) == "quota_exhausted"
                and fallback_model
                and fallback_model != settings.rm_judgment_model
            ):
                return await run_session(client, quota, bundle, settings, model=fallback_model)  # type: ignore[arg-type]
            classification = classify_error(failed.cause)
            if not (classification.retryable and classification.action == "retry"):
                raise
            if attempt + 1 < RETRYABLE_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_S)
    assert last is not None
    raise last


def _fail_open(
    row: ReturnedRow, before: BeforeRow | None, reason: str, *, attempted_model_call: bool = False
) -> RowResult:
    """Every non-success path ends here: `uncertain` / `pending_review`, the reason in
    `failure_reason`, and no detail (there is no real judgment to show)."""
    return RowResult(_uncertain_row(row, before, reason), reason, attempted_model_call)


def _report_progress(on_progress: Any | None, *args: Any) -> None:
    if on_progress is None:
        return
    try:
        on_progress(*args)
    except Exception:  # a progress-reporting failure must never stop the batch
        logger.warning("batch progress callback failed", exc_info=True)


async def process_returned_row(
    row: ReturnedRow,
    before_by_unit: dict[str, BeforeRow],
    *,
    settings: Settings,
    client: ModelClient,
    http_client: httpx.AsyncClient,
    quota: _NoDbQuota,
    default_category: str | None,
    list_price_minor: int,
) -> RowResult:
    before = before_by_unit.get(row.unit_id)
    if before is None:
        return _fail_open(row, None, "no_before_record")
    if not before.photo_ref:
        return _fail_open(row, before, "no_reference_photo")
    if not row.returned_photo_refs:
        return _fail_open(row, before, "no_return_photo")

    category = before.category or default_category
    if not category:
        return _fail_open(row, before, "no_category")
    category = category.lower()
    if category not in VALID_CATEGORIES:
        return _fail_open(row, before, f"unknown_category:{category}")

    try:
        rubric = load_rubric(category)
        policy = load_policy(category)
    except ValueError as exc:
        return _fail_open(row, before, f"reference_load_failed:{exc}")

    parts = parse_parts_list(before.parts_list)
    card = build_card(
        org_id=before.org_id or row.org_id,
        sku=before.ordered_sku or row.ordered_sku,
        asin=before.ordered_asin or row.ordered_asin,
        category_key=category,
        parts=parts,
        list_price_minor=list_price_minor,
    )

    long_edge = settings.rm_analysis_long_edge
    try:
        ref_bytes = await fetch_image(before.photo_ref, http_client, long_edge=long_edge)
    except ImageFetchError as exc:
        return _fail_open(row, before, f"image_fetch_failed:{exc}")

    # One bad URL among several must not discard every other, usable return photo (§3 fail
    # open: preserve the available information). Only if literally none of them fetch does
    # the whole row fail open.
    return_bytes: list[bytes] = []
    photo_errors: list[str] = []
    for url in row.returned_photo_refs:
        try:
            return_bytes.append(await fetch_image(url, http_client, long_edge=long_edge))
        except ImageFetchError as exc:
            photo_errors.append(str(exc))
    if not return_bytes:
        return _fail_open(row, before, f"image_fetch_failed:{'; '.join(photo_errors)}")

    photos = [
        ReturnPhoto(
            alias=f"P{i + 1}",
            photo_id=f"batch-{row.record_id}-{i + 1}",
            sha256_analysis=sha256_hex(data),
            analysis_bytes=data,
            original_bytes=data,
            quality_status="ok",
            barcodes=(),
            gate_issues=(),
        )
        for i, data in enumerate(return_bytes)
    ]
    refs = [("ref_before", "front", sha256_hex(ref_bytes), ref_bytes)]

    bundle = assemble(
        settings=settings,
        return_row={"return_id": row.record_id, "order_id": row.order_id},
        card=card,
        other_cards={},
        rubric=rubric,
        policy=policy,
        photos=photos,
        refs=refs,
    )

    if quota.is_exhausted:
        # Quota was used up earlier in this run: no request is sent, and nothing is guessed.
        return _fail_open(row, before, "model_call_failed:quota_exhausted")

    try:
        session = await _run_judgment_with_fallback(client, bundle, settings, quota)
    except SessionFailed as exc:
        error_class = classify_error(exc.cause).error_class
        if error_class == "quota_exhausted":
            await quota.mark_exhausted(settings.rm_judgment_model, "judgment")
        return _fail_open(row, before, f"model_call_failed:{error_class}", attempted_model_call=True)

    result = run_pipeline(
        session.judgment,
        bundle.ctx,
        photo_gate=PhotoGate(non_fail_photos=len(photos), acknowledged_warnings=False),
        rules_version="batch-import-v1",
    )

    id_check = check_id_match(before, row)
    disposition = _disposition_for_id_check(
        before, id_check, result.decision.recommended_disposition or "pending_review"
    )

    output_row = {
        "record_id": row.record_id,
        "unit_id": row.unit_id,
        "org_id": row.org_id,
        "order_id": row.order_id,
        "ordered_sku": row.ordered_sku,
        "ordered_asin": row.ordered_asin,
        "identity_match": before.identity_match,  # carried forward, not re-derived (per instruction)
        # The model's own identity verdict on the returned photo(s), kept separate (F-024).
        "photo_identity_match": session.judgment.identity.identity_match,
        "parts_list": before.parts_list,
        "parts_missing": _missing_parts_field(result.completeness),
        "observed_state": session.judgment.model_observed_state,
        "amazon_condition": result.condition.amazon_condition,
        "operator_disposition": disposition,
        "photo_refs": ";".join(row.returned_photo_refs),
        "captured_at": row.time,
        "sold_vs_returned_id_check": id_check,
        "failure_reason": "",
    }
    warning = (
        f"{len(photo_errors)} of {len(row.returned_photo_refs)} return photo(s) failed to fetch: "
        + "; ".join(photo_errors)
        if photo_errors
        else None
    )
    detail = _build_row_detail(session_judgment=session.judgment, result=result, row=row, before=before)
    return RowResult(output_row, None, True, warning, detail=detail)


async def run_batch(
    *,
    before_path: Path,
    returned_path: Path,
    settings: Settings,
    client: ModelClient,
    default_category: str | None = None,
    list_price_minor: int = 999900,
    max_requests: int | None = None,
    on_progress: Any | None = None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]], BatchSummary]:
    """Returns `(output_rows, details_by_record_id, summary)`. `details_by_record_id` only has an
    entry for a row that reached a genuine successful pipeline run (see `RowResult.detail`)."""
    before_by_unit = read_before_csv(before_path)
    returned_rows = read_returned_csv(returned_path)
    summary = BatchSummary(total_rows=len(returned_rows))
    output_rows: list[dict[str, str]] = []
    details_by_record_id: dict[str, dict[str, Any]] = {}
    quota = _NoDbQuota(settings.rm_rpm_limit_judgment)

    headers = {"User-Agent": "ReturnsManagerBatchTool/1.0 (Cube Buildathon 04; standalone batch import)"}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as http_client:
        for row in returned_rows:
            if max_requests is not None and summary.live_requests >= max_requests:
                unc = _uncertain_row(row, before_by_unit.get(row.unit_id), "max_requests_reached")
                output_rows.append(unc)
                summary.uncertain += 1
                summary.notes.append(f"{row.record_id}: skipped, max_requests reached")
                _report_progress(on_progress, unc, None, summary, output_rows, details_by_record_id)
                continue
            result = await process_returned_row(
                row,
                before_by_unit,
                settings=settings,
                client=client,
                http_client=http_client,
                quota=quota,
                default_category=default_category,
                list_price_minor=list_price_minor,
            )
            output_rows.append(result.output_row)
            if result.detail is not None:
                details_by_record_id[row.record_id] = result.detail
            if result.attempted_model_call:
                summary.live_requests += 1
            if result.note is None:
                summary.processed += 1
                if result.warning:
                    summary.notes.append(f"{row.record_id}: processed with warning: {result.warning}")
            else:
                summary.uncertain += 1
                summary.notes.append(f"{row.record_id}: {result.note}")
            _report_progress(on_progress, result.output_row, result.detail, summary, output_rows, details_by_record_id)
    return output_rows, details_by_record_id, summary


def run_batch_sync(
    **kwargs: Any,
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]], BatchSummary]:
    return asyncio.run(run_batch(**kwargs))
