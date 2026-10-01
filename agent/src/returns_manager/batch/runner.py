"""Orchestrates one batch run: join before/returned rows, download photos, run the real
judgment session + deterministic pipeline per return, write one output CSV row each.

No database, no job queue. Every row fails open: a download error, a missing before-
record, an unmapped category or a model/provider failure never crashes the run and never
guesses a verdict - that row is written as `observed_state=uncertain`,
`operator_disposition=pending_review` with the reason logged, and the run continues.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from returns_manager.batch import auto_approve
from returns_manager.batch.cards import (
    DEFAULT_LIST_PRICE_MINOR,
    VALID_CATEGORIES,
    build_card,
    normalize_category,
)
from returns_manager.batch.images import ImageFetchError, fetch_image
from returns_manager.batch.io_csv import (
    VALUE_SOURCE_CSV,
    VALUE_SOURCE_DEFAULT,
    BeforeRow,
    ReturnedRow,
    read_before_csv,
    read_returned_csv,
)
from returns_manager.batch.parts import parse_parts_list
from returns_manager.canonical.hashing import sha256_hex
from returns_manager.config import REPO_ROOT, Settings
from returns_manager.db.pool import Database
from returns_manager.errors import QuotaExhaustedError
from returns_manager.jobs.budget import TokenBucketRateLimiter
from returns_manager.jobs.retry import classify_error
from returns_manager.judgment.pipeline import PhotoGate, run_pipeline
from returns_manager.judgment.types import EffectivePolicy
from returns_manager.llm.client import ModelClient
from returns_manager.llm.context import ContextBundle, ReturnPhoto, assemble
from returns_manager.llm.loop import SessionFailed, run_session
from returns_manager.llm.quota import QuotaGuard, Role
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
    quota: _NoDbQuota

    async def take(self) -> None:
        """Called by the session loop right before each request is sent: the run's request cap
        is checked here, so a request beyond `--max-requests` is refused, never sent."""
        if self.quota.cap_reached:
            raise RequestCapReached(f"run request cap of {self.quota.max_requests} reached")
        await self.limiter.acquire(timeout_s=120)
        self.quota.requests_sent += 1


class RequestCapReached(QuotaExhaustedError):
    """This run's `--max-requests` cap is used up. Raised before a request is sent."""


class _NoDbQuota:
    """Same shape as llm.quota.QuotaGuard, without a database - this run is standalone.

    There is no daily-budget ledger here; `--max-requests` on the CLI is this run's own
    spend guard instead. It caps real requests (every session round trip and retry counts),
    not rows, and `requests_sent` is the count reported as "live model requests used".
    It still throttles requests per minute per model with the same
    `TokenBucketRateLimiter` the real QuotaGuard uses - one instance shared across the whole
    run (never per-row: a fresh limiter every row would never actually pace anything), so a
    batch of many rows on a fresh key does not immediately trip Gemini's own per-minute
    rate limit the way an unthrottled loop does.
    """

    def __init__(self, rpm: float, max_requests: int | None = None) -> None:
        self._rpm = rpm
        self._limiters: dict[str, TokenBucketRateLimiter] = {}
        self.is_exhausted: bool = False
        self.max_requests = max_requests
        self.requests_sent = 0

    @property
    def cap_reached(self) -> bool:
        return self.max_requests is not None and self.requests_sent >= self.max_requests

    def _limiter(self, model_id: str) -> TokenBucketRateLimiter:
        if model_id not in self._limiters:
            limiter = TokenBucketRateLimiter(self._rpm)
            limiter.tokens = 0.0
            self._limiters[model_id] = limiter
        return self._limiters[model_id]

    @asynccontextmanager
    async def reserve(self, model_id: str, role: Role, n: int) -> AsyncIterator[_NoDbReservation]:
        if self.is_exhausted:
            raise QuotaExhaustedError("daily request quota used up")
        if self.cap_reached:
            raise RequestCapReached(f"run request cap of {self.max_requests} reached")
        yield _NoDbReservation(self._limiter(model_id), self)

    async def mark_exhausted(self, model_id: str, role: Role) -> None:
        self.is_exhausted = True


class _BatchQuota:
    """Database-backed quota with the same API as the in-memory batch quota stub.

    The real batch path should reserve and release live model requests through the existing
    `QuotaGuard` ledger so `quota status` reflects the truth. The CLI/no-db path remains for
    standalone batch runs that intentionally do not touch Postgres.
    """

    def __init__(self, db: Database, settings: Settings, max_requests: int | None = None) -> None:
        self._db = db
        self._settings = settings
        self._guard = QuotaGuard(db, settings)
        self._fallback = _NoDbQuota(settings.rm_rpm_limit_judgment, max_requests=max_requests)
        self.max_requests = max_requests
        self.requests_sent = 0
        self.is_exhausted = False

    @property
    def cap_reached(self) -> bool:
        return self.max_requests is not None and self.requests_sent >= self.max_requests

    @asynccontextmanager
    async def reserve(self, model_id: str, role: Role, n: int) -> AsyncIterator[Any]:
        if self.is_exhausted:
            raise QuotaExhaustedError("daily request quota used up")
        if self.cap_reached:
            raise RequestCapReached(f"run request cap of {self.max_requests} reached")

        class _Reservation:
            def __init__(self, quota: _BatchQuota, inner: Any) -> None:
                self.quota = quota
                self.inner = inner

            async def take(self) -> None:
                if (
                    self.quota.max_requests is not None
                    and self.quota.requests_sent >= self.quota.max_requests
                ):
                    raise RequestCapReached(f"run request cap of {self.quota.max_requests} reached")
                await self.inner.take()
                self.quota.requests_sent += 1

        async with self._guard.reserve(model_id, role, n) as reservation:
            yield _Reservation(self, reservation)

    async def mark_exhausted(self, model_id: str, role: Role) -> None:
        self.is_exhausted = True
        await self._guard.mark_exhausted(model_id, role)


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


ID_CHECK_FIELDS = ("org_id", "order_id", "ordered_sku", "ordered_asin")


def check_id_match(before: BeforeRow | None, row: ReturnedRow) -> str:
    """Do the IDs on the *returned* record actually match the IDs recorded when this same
    unit was *sold*? This is a plain data check, independent of anything a photo shows -
    a returned package can carry the wrong order number or SKU on its label even when the
    photo inside it is completely genuine, and a photo-based identity match can't catch
    that. Compares every id the two records both carry; any disagreement is reported, not
    just the first one found, so a human reviewing this doesn't have to re-check by hand.

    "matched" means every ID field was present on both records and agreed. A field blank on
    either side is not evidence of a match: it is reported as "not checked: <field> missing".
    """
    if before is None:
        return "NOT MATCHED: no sold-record for this unit_id"
    mismatches: list[str] = []
    not_checked: list[str] = []
    for name in ID_CHECK_FIELDS:
        sold, returned = getattr(before, name), getattr(row, name)
        blank = [side for side, value in (("sold", sold), ("returned", returned)) if not value]
        if blank:
            not_checked.append(f"{name} missing ({' and '.join(blank)})")
        elif sold != returned:
            mismatches.append(f"{name}: sold={sold!r} vs returned={returned!r}")
    parts: list[str] = []
    if mismatches:
        parts.append("NOT MATCHED: " + "; ".join(mismatches))
    if not_checked:
        parts.append("not checked: " + "; ".join(not_checked))
    return " | ".join(parts) if parts else "matched"


# Engine outcomes that depend on the list price: S02 (high-value sign-off), R09 (refurbish only
# if the net gain clears the threshold) and R10 (liquidate vs dispose by salvage value).
VALUE_DRIVEN_RULES = ("R09", "R10")
VALUE_DRIVEN_SIGNOFFS = ("S02_high_value",)


def _value_source(before: BeforeRow | None) -> str:
    if before is None:
        return ""
    return VALUE_SOURCE_CSV if before.list_price_minor is not None else VALUE_SOURCE_DEFAULT


def _list_price(before: BeforeRow, default_minor: int) -> int:
    return before.list_price_minor if before.list_price_minor is not None else default_minor


def value_record(before: BeforeRow, default_minor: int, decision: Any) -> dict[str, Any]:
    """Where the numbers behind a value-driven outcome came from, for the row detail. The UI shows
    "price assumed (synthetic)" from `value_source`; it never works this out itself. Recovery
    rates and refurbish cost are always the synthetic placeholders in batch/cards.py."""
    outcomes = [decision.rule_id] if decision.rule_id in VALUE_DRIVEN_RULES else []
    outcomes += [s for s in decision.signoff_reasons if s in VALUE_DRIVEN_SIGNOFFS]
    return {
        "list_price_minor": _list_price(before, default_minor),
        "currency": "INR",
        "value_source": _value_source(before),
        "recovery_rates_source": VALUE_SOURCE_DEFAULT,
        "refurbish_cost_source": VALUE_SOURCE_DEFAULT,
        "value_driven_outcomes": outcomes,
    }


REFERENCE_ALIAS = "ref_before"


def photo_aliases(reference_url: str, fetched_return_urls: list[str]) -> dict[str, str]:
    """The photo alias the model saw -> the URL it came from. Return photos are numbered P1, P2...
    in the order they were *fetched*, so a URL that failed to download shifts the numbering; the
    UI must use this map and never assume Pn is the n-th URL in the CSV."""
    aliases = {REFERENCE_ALIAS: reference_url}
    aliases.update({f"P{i + 1}": url for i, url in enumerate(fetched_return_urls)})
    return aliases


def comparison_record(
    card: Any, judgment: Any, aliases: dict[str, str], unfetched: list[str]
) -> dict[str, Any]:
    """Everything the Inspection comparison panel shows beyond the fused results already in the
    detail: the card's distinguishing features joined with the model's own check for each, and
    plain counts of the critical ones. No score or percentage: the model reports none."""
    checks = {fc.feature_id: fc for fc in judgment.identity.feature_checks}
    features: list[dict[str, Any]] = []
    for f in card.distinguishing_features:
        fc = checks.get(f.id)
        features.append(
            {
                "feature_id": f.id,
                "description": f.description,
                "importance": f.importance,
                "location": f.location,
                "result": fc.result if fc else "not_reported",
                "photo": fc.photo if fc else None,
            }
        )
    critical = [f for f in features if f["importance"] == "critical"]
    return {
        "photo_aliases": aliases,
        "unfetched_photo_refs": list(unfetched),
        "features": features,
        "critical_features": {
            "total": len(critical),
            "matched": sum(1 for f in critical if f["result"] == "match"),
            "mismatched": sum(1 for f in critical if f["result"] == "mismatch"),
            "not_visible": sum(1 for f in critical if f["result"] == "not_visible"),
            "not_reported": sum(1 for f in critical if f["result"] == "not_reported"),
        },
    }


def _operator_disposition(recommended: str | None, *, auto_approved: bool) -> str:
    """`operator_disposition` before any human decision (§14.3): the engine's route only when the
    row is auto-approved (engine route, no review, no sign-off, IDs agree - see auto_approve.py);
    otherwise `pending_review`. A proven ID or image mismatch is separately recorded as
    `auto_disapproved`; it is not a fifth disposition route."""
    if auto_approved and recommended:
        return recommended
    return "pending_review"


def _id_mismatch(before: BeforeRow | None, id_check: str) -> bool:
    """A proven disagreement between the sold and returned records. No sold record at all is a
    missing-data problem (the row fails open for that), not a proven mismatch."""
    return before is not None and id_check.startswith("NOT MATCHED")


def _id_not_checked(id_check: str) -> bool:
    """At least one ID field was blank on one side, so the records were not fully compared."""
    return "not checked:" in id_check


def _is_auto_disapproved(before: BeforeRow | None, row: ReturnedRow, photo_identity_match: str) -> bool:
    """Only a proven paperwork or visual identity mismatch is an automatic disapproval."""
    return _id_mismatch(before, check_id_match(before, row)) or photo_identity_match == "no"


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
        "identity_match": before.identity_match if before else "",  # nothing to carry forward
        "photo_identity_match": "uncertain",  # no model verdict on the returned photo this run
        "parts_list": before.parts_list if before else "",
        "parts_missing": "",
        "observed_state": "uncertain",
        "amazon_condition": "uncertain",
        "operator_disposition": "pending_review",
        "agent_disposition": "",
        "auto_approved": "false",
        "auto_disapproved": "true" if _is_auto_disapproved(before, row, "uncertain") else "false",
        "photo_refs": ";".join(row.returned_photo_refs),
        "captured_at": row.time,
        "sold_vs_returned_id_check": id_check,
        "failure_reason": reason,
        # A fail-open row is not a real decision, so it must not claim a CSV-backed or synthetic
        # value source that implies a model-derived price/condition outcome.
        "value_source": "",
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
            if isinstance(failed.cause, RequestCapReached):
                raise  # the run's cap covers every model; a fallback or retry would be refused too
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
    except OSError:  # a failed progress write must not stop the batch; anything else is a bug
        logger.warning("batch progress callback failed", exc_info=True)


async def process_returned_row(
    row: ReturnedRow,
    before_by_unit: dict[str, BeforeRow],
    *,
    settings: Settings,
    client: ModelClient,
    http_client: httpx.AsyncClient,
    quota: Any,
    default_category: str | None,
    list_price_minor: int,
) -> RowResult:
    before = before_by_unit.get(row.unit_id)
    if before is None:
        return _fail_open(row, None, "no_before_record")
    if not before.photo_ref:
        return _fail_open(row, before, "no_reference_photo")

    # Single-photo mode: no return photo was supplied in the CSV, but we can still run the AI
    # on the sold/reference photo alone.  Confidence is automatically reduced: PhotoGate will
    # report non_fail_photos=1, the photo_quality check will be FAIL, auto-approve is blocked,
    # and failure_reason is set to signal the reduced-confidence result to the UI.
    # The AI can still determine identity (same product?), condition, and damage from a single
    # image and will produce a real disposition rather than defaulting to uncertain/pending.
    _single_photo_mode = not row.returned_photo_refs

    category = before.category or default_category
    if not category:
        return _fail_open(row, before, "no_category")
    category = normalize_category(category)
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
        list_price_minor=_list_price(before, list_price_minor),
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
    fetched_urls: list[str] = []
    unfetched_urls: list[str] = []
    photo_errors: list[str] = []
    for url in row.returned_photo_refs:
        try:
            return_bytes.append(await fetch_image(url, http_client, long_edge=long_edge))
            fetched_urls.append(url)
        except ImageFetchError as exc:
            photo_errors.append(str(exc))
            unfetched_urls.append(url)
    if not return_bytes:
        if _single_photo_mode:
            # No return URLs were provided at all; use the reference photo as the sole
            # return image so the AI can still produce a real verdict.
            return_bytes = [ref_bytes]
            fetched_urls = [before.photo_ref]
        else:
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
    refs = [(REFERENCE_ALIAS, "front", sha256_hex(ref_bytes), ref_bytes)]

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
    if quota.cap_reached:
        return _fail_open(row, before, "max_requests_reached")

    try:
        session = await _run_judgment_with_fallback(client, bundle, settings, quota)
    except SessionFailed as exc:
        if isinstance(exc.cause, RequestCapReached):
            # The cap stopped this row mid-session (e.g. before a tool round trip); any request
            # already sent is counted, and the row is not judged.
            return _fail_open(
                row, before, "max_requests_reached", attempted_model_call=exc.trace.requests_sent > 0
            )
        error_class = classify_error(exc.cause).error_class
        if error_class == "quota_exhausted":
            await quota.mark_exhausted(settings.rm_judgment_model, "judgment")
        return _fail_open(row, before, f"model_call_failed:{error_class}", attempted_model_call=True)

    # In single-photo mode, non_fail_photos=1 triggers a photo_quality FAIL check,
    # which blocks auto-approve and surfaces in the UI as a reduced-confidence signal.
    _effective_non_fail_photos = 1 if _single_photo_mode else len(photos)
    result = run_pipeline(
        session.judgment,
        bundle.ctx,
        photo_gate=PhotoGate(non_fail_photos=_effective_non_fail_photos, acknowledged_warnings=False),
        rules_version="batch-import-v1",
    )

    id_check = check_id_match(before, row)
    id_mismatch = _id_mismatch(before, id_check)
    auto_disapproved = _is_auto_disapproved(before, row, result.identity.identity_match)
    # A wrong item (model identity "no") is §12.2 R03 and has no disposition route. It is
    # separately auto-disapproved; a sold-vs-returned paperwork mismatch has the same outcome.
    approval = auto_approve.evaluate(
        result,
        id_mismatch=id_mismatch,
        id_not_checked=_id_not_checked(id_check),
        threshold_bp=settings.rm_batch_auto_approve_min_confidence_bp,
    )
    disposition = _operator_disposition(
        result.decision.recommended_disposition, auto_approved=approval.approved
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
        "photo_identity_match": result.judgment.identity.identity_match,
        "parts_list": before.parts_list,
        "parts_missing": _missing_parts_field(result.completeness),
        "observed_state": result.judgment.model_observed_state,
        "amazon_condition": result.condition.amazon_condition,
        "operator_disposition": disposition,
        "agent_disposition": result.decision.recommended_disposition or "",
        "auto_approved": "true" if approval.approved else "false",
        "auto_disapproved": "true" if auto_disapproved else "false",
        # In single-photo mode, record the reference URL so the UI knows which image was used.
        "photo_refs": before.photo_ref if _single_photo_mode else ";".join(row.returned_photo_refs),
        "captured_at": row.time,
        "sold_vs_returned_id_check": id_check,
        # In single-photo mode, tag the row so the UI can show a reduced-confidence notice.
        # This is NOT a fail-open: a real model verdict was produced, just with one image.
        "failure_reason": (
            "single_photo_mode:no_return_photo_supplied;reference_image_used_as_proxy;"
            "confidence_reduced;operator_review_recommended"
            if _single_photo_mode
            else ""
        ),
        "value_source": _value_source(before),
    }
    # Build the warning string.  In single-photo mode the reduced-confidence message is already
    # in failure_reason; any URL-fetch errors (from the normal multi-photo path) are appended too.
    warning_parts: list[str] = []
    if _single_photo_mode:
        warning_parts.append(
            "Single-photo mode: no return photo supplied. "
            "Reference (before-sale) image used as proxy. "
            "Confidence is reduced; operator review is recommended."
        )
    if photo_errors:
        warning_parts.append(
            f"{len(photo_errors)} of {len(row.returned_photo_refs)} return photo(s) failed to fetch: "
            + "; ".join(photo_errors)
        )
    warning = " | ".join(warning_parts) if warning_parts else None
    detail = _build_row_detail(session_judgment=result.judgment, result=result, row=row, before=before)
    detail["auto_approval"] = approval.as_dict()
    detail["single_photo_mode"] = _single_photo_mode
    detail["value"] = value_record(before, list_price_minor, result.decision)
    detail["comparison"] = comparison_record(
        card, result.judgment, photo_aliases(before.photo_ref, fetched_urls), unfetched_urls
    )
    return RowResult(output_row, None, True, warning, detail=detail)


async def run_batch(
    *,
    before_path: Path,
    returned_path: Path,
    settings: Settings,
    client: ModelClient,
    default_category: str | None = None,
    list_price_minor: int = DEFAULT_LIST_PRICE_MINOR,
    max_requests: int | None = None,
    on_progress: Any | None = None,
    db: Database | None = None,
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]], BatchSummary]:
    """Returns `(output_rows, details_by_record_id, summary)`. `details_by_record_id` only has an
    entry for a row that reached a genuine successful pipeline run (see `RowResult.detail`)."""
    before_by_unit = read_before_csv(before_path)
    returned_rows = read_returned_csv(returned_path)
    summary = BatchSummary(total_rows=len(returned_rows))
    output_rows: list[dict[str, str]] = []
    details_by_record_id: dict[str, dict[str, Any]] = {}
    quota: Any = (
        _BatchQuota(db, settings, max_requests=max_requests)
        if db is not None
        else _NoDbQuota(settings.rm_rpm_limit_judgment, max_requests=max_requests)
    )

    headers = {"User-Agent": "ReturnsManagerBatchTool/1.0 (Cube Buildathon 04; standalone batch import)"}
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as http_client:
        for row in returned_rows:
            if quota.cap_reached:
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
            summary.live_requests = quota.requests_sent  # real requests, not rows
            if result.note is None:
                summary.processed += 1
                if result.warning:
                    summary.notes.append(f"{row.record_id}: processed with warning: {result.warning}")
            else:
                summary.uncertain += 1
                summary.notes.append(f"{row.record_id}: {result.note}")
            _report_progress(
                on_progress, result.output_row, result.detail, summary, output_rows, details_by_record_id
            )
    return output_rows, details_by_record_id, summary


def run_batch_sync(
    **kwargs: Any,
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]], BatchSummary]:
    return asyncio.run(run_batch(**kwargs))
