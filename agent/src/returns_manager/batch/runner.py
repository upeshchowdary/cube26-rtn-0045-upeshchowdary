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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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

    def _limiter(self, model_id: str) -> TokenBucketRateLimiter:
        if model_id not in self._limiters:
            limiter = TokenBucketRateLimiter(self._rpm)
            # TokenBucketRateLimiter starts its bucket full, which is right for the real
            # long-running worker (it has already been pacing prior requests) but wrong here:
            # this tool always starts cold, so a full bucket lets the first `rpm` requests of
            # a run fire as one instant burst - which a fresh key's real per-minute limit can
            # still reject even though the sustained rate is within budget (confirmed live:
            # 9 of 12 rows hit 429 rate-limited before this fix). Draining it to empty at
            # construction paces every request in the run evenly from the very first one.
            limiter.tokens = 0.0
            self._limiters[model_id] = limiter
        return self._limiters[model_id]

    @asynccontextmanager
    async def reserve(self, model_id: str, role: str, n: int) -> AsyncIterator[_NoDbReservation]:
        yield _NoDbReservation(self._limiter(model_id))

    async def mark_exhausted(self, model_id: str, role: str) -> None:
        return None


@dataclass
class RowResult:
    output_row: dict[str, str]
    note: str | None  # None on a clean success; otherwise why the row is a fail-open uncertain
    attempted_model_call: bool  # True iff a live request actually left this machine for this row
    warning: str | None = None  # non-fatal issue on an otherwise-successful row (e.g. one of
    # several photo URLs failed but enough others fetched to still judge the return)


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


def _uncertain_row(row: ReturnedRow, before: BeforeRow | None, reason: str) -> dict[str, str]:
    return {
        "record_id": row.record_id,
        "unit_id": row.unit_id,
        "org_id": row.org_id,
        "order_id": row.order_id,
        "ordered_sku": row.ordered_sku,
        "ordered_asin": row.ordered_asin,
        "identity_match": before.identity_match if before else "uncertain",
        "parts_list": before.parts_list if before else "",
        "parts_missing": "",
        "observed_state": "uncertain",
        "amazon_condition": "uncertain",
        "operator_disposition": "pending_review",
        "photo_refs": ";".join(row.returned_photo_refs),
        "captured_at": row.time,
        "sold_vs_returned_id_check": check_id_match(before, row),
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
        return RowResult(
            _uncertain_row(row, None, "no before-record for this unit_id"), "no_before_record", False
        )
    if not before.photo_ref:
        return RowResult(
            _uncertain_row(row, before, "before-record has no photo_ref"), "no_reference_photo", False
        )
    if not row.returned_photo_refs:
        return RowResult(_uncertain_row(row, before, "no returned_photo_ref"), "no_return_photo", False)

    category = before.category or default_category
    if not category:
        return RowResult(
            _uncertain_row(row, before, "no category given and no --default-category"), "no_category", False
        )
    category = category.lower()
    if category not in VALID_CATEGORIES:
        return RowResult(
            _uncertain_row(row, before, f"unknown category {category!r}"),
            f"unknown_category:{category}",
            False,
        )

    try:
        rubric = load_rubric(category)
        policy = load_policy(category)
    except ValueError as exc:
        return RowResult(_uncertain_row(row, before, str(exc)), f"reference_load_failed:{exc}", False)

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
        return RowResult(_uncertain_row(row, before, str(exc)), f"image_fetch_failed:{exc}", False)

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
        return RowResult(
            _uncertain_row(row, before, "; ".join(photo_errors)),
            f"image_fetch_failed:{'; '.join(photo_errors)}",
            False,
        )

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

    try:
        session = await _run_judgment_with_fallback(client, bundle, settings, quota)
    except SessionFailed as exc:
        return RowResult(
            _uncertain_row(row, before, str(exc.cause)), f"model_session_failed:{exc.cause}", True
        )

    result = run_pipeline(
        session.judgment,
        bundle.ctx,
        photo_gate=PhotoGate(non_fail_photos=len(photos), acknowledged_warnings=False),
        rules_version="batch-import-v1",
    )

    # operator_disposition carries the engine's actual computed route whenever it computed
    # one at all (restock/refurbish/liquidate/dispose) - exactly like the real
    # rm.returns.disposition column would, and like data/returns_sample.csv's own rows (most
    # of which show a specific route even though a human still had to action it). It falls
    # back to "pending_review" only when the engine could not compute any route (identity
    # unresolved, item not present, condition ungraded, ...) - not merely because the route
    # also needs a human sign-off, which the disposition-params high-value threshold makes
    # true for almost every non-restock route at realistic prices. requires_review /
    # requires_signoff are real, additional facts the engine records; collapsing every one of
    # them into the same "pending_review" string was throwing that decision away.
    disposition = result.decision.recommended_disposition or "pending_review"

    output_row = {
        "record_id": row.record_id,
        "unit_id": row.unit_id,
        "org_id": row.org_id,
        "order_id": row.order_id,
        "ordered_sku": row.ordered_sku,
        "ordered_asin": row.ordered_asin,
        "identity_match": before.identity_match,  # carried forward, not re-derived (per instruction)
        "parts_list": before.parts_list,
        "parts_missing": _missing_parts_field(result.completeness),
        "observed_state": session.judgment.model_observed_state,
        "amazon_condition": result.condition.amazon_condition,
        "operator_disposition": disposition,
        "photo_refs": ";".join(row.returned_photo_refs),
        "captured_at": row.time,
        "sold_vs_returned_id_check": check_id_match(before, row),
    }
    warning = (
        f"{len(photo_errors)} of {len(row.returned_photo_refs)} return photo(s) failed to fetch: "
        + "; ".join(photo_errors)
        if photo_errors
        else None
    )
    return RowResult(output_row, None, True, warning)


async def run_batch(
    *,
    before_path: Path,
    returned_path: Path,
    settings: Settings,
    client: ModelClient,
    default_category: str | None = None,
    list_price_minor: int = 999900,
    max_requests: int | None = None,
) -> tuple[list[dict[str, str]], BatchSummary]:
    before_by_unit = read_before_csv(before_path)
    returned_rows = read_returned_csv(returned_path)
    summary = BatchSummary(total_rows=len(returned_rows))
    output_rows: list[dict[str, str]] = []
    quota = _NoDbQuota(settings.rm_rpm_limit_judgment)

    headers = {"User-Agent": "ReturnsManagerBatchTool/1.0 (Cube Buildathon 04; standalone batch import)"}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as http_client:
        for row in returned_rows:
            if max_requests is not None and summary.live_requests >= max_requests:
                output_rows.append(
                    _uncertain_row(row, before_by_unit.get(row.unit_id), "max_requests reached")
                )
                summary.uncertain += 1
                summary.notes.append(f"{row.record_id}: skipped, max_requests reached")
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
            if result.attempted_model_call:
                summary.live_requests += 1
            if result.note is None:
                summary.processed += 1
                if result.warning:
                    summary.notes.append(f"{row.record_id}: processed with warning: {result.warning}")
            else:
                summary.uncertain += 1
                summary.notes.append(f"{row.record_id}: {result.note}")
    return output_rows, summary


def run_batch_sync(**kwargs: Any) -> tuple[list[dict[str, str]], BatchSummary]:
    return asyncio.run(run_batch(**kwargs))
