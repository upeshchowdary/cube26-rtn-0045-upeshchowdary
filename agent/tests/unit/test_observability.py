"""T-OBS-* tests for Phase 11 (§18: logging/redaction, metrics, economics, spend guards).

  T-OBS-01  parse_window / window_since accept "24h"/"7d"/"all" and reject garbage.
  T-OBS-02  metric() renders n=0 as the literal "no data", never a bare 0 or null value.
  T-OBS-03  MetricsService.summary() on a brand-new org returns "no data" for every metric.
  T-OBS-04  throughput_per_hour, requests/tool-calls-per-inspection, model_latency_ms,
            capture_to_decision_ms compute real numbers from real inserted rows.
  T-OBS-05  uncertain_rate, disposition_distribution and integrity_counters over a real
            mixed population.
  T-OBS-06  EconomicsService.cost_by_stage / cost_per_inspection convert real
            cost_usd_micros correctly (USD and INR, against the real fx.yaml rate).
  T-OBS-07  EconomicsService.recovery_uplift reads a real disposition_engine decision's
            expected_recovery_minor and computes the synthetic uplift over the baseline.
  T-OBS-08  preflight_bulk_spend: quota-days guard and spend-cap guard, both with and
            without their override flags.

Redaction (T-SEC-09) lives in test_db_security.py, next to the other security tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

from returns_manager.db.pool import Database
from returns_manager.observability.economics import EconomicsService, load_fx, usd_to_inr
from returns_manager.observability.metrics import MetricsService, metric, parse_window, window_since
from returns_manager.observability.spend_guard import preflight_bulk_spend

pytestmark = pytest.mark.db


def _fresh_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _fresh_org_id() -> str:
    # org_id has its own stricter charset (db/tenant.py ORG_ID_RE): no hyphens.
    return f"org_obs{uuid.uuid4().hex[:12]}"


# ── T-OBS-01/02: pure helpers, no DB ────────────────────────────────────────────


def test_t_obs_01_parse_window() -> None:
    assert parse_window("24h").total_seconds() == 24 * 3600
    assert parse_window("7d").days == 7
    assert parse_window("all") is None
    assert window_since("all") is None
    assert window_since("1h") is not None
    for bad in ("", "7", "d7", "7x", "-1d", "0h"):
        with pytest.raises(ValueError, match="window"):
            parse_window(bad)


def test_t_obs_02_metric_no_data_vs_zero() -> None:
    zero_rate = metric(0.0, 5, "7d", "some rate")
    assert zero_rate.value == 0.0, "a real zero must stay 0.0, not 'no data'"
    assert zero_rate.n == 5

    empty = metric(0.0, 0, "7d", "some rate")
    assert empty.value == "no data"
    assert empty.n == 0


# ── DB fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def obs_org(db: Database) -> str:
    org = _fresh_org_id()
    async with db.transaction(org) as conn:
        await conn.execute("INSERT INTO rm.organizations (org_id, name) VALUES (%s, 'obs test')", (org,))
    return org


async def _make_return(db: Database, org: str, *, submitted: bool, finalized: bool) -> str:
    unit_id = _fresh_id("UNIT-OBS")
    order_id = _fresh_id("ORD-OBS")
    return_id = _fresh_id("ret-obs")
    record_id = f"RTN-{uuid.uuid4().int % 9000 + 1000:04d}"
    async with db.transaction(org) as conn:
        await conn.execute(
            "INSERT INTO rm.orders (org_id, order_id, unit_id, ordered_sku, quantity, "
            "fulfilment_route, ordered_at) VALUES (%s, %s, %s, 'SKU-LAMP-LED', 1, 'fba', now())",
            (org, order_id, unit_id),
        )
        await conn.execute(
            "INSERT INTO rm.returns (return_id, org_id, record_id, unit_id, order_id, "
            "return_seq, created_by, status, submitted_at, finalized_at) "
            "VALUES (%s, %s, %s, %s, %s, 1, 'test', %s, %s, %s)",
            (
                return_id,
                org,
                record_id,
                unit_id,
                order_id,
                "finalized" if finalized else "inspecting",
                datetime.now(UTC) - timedelta(minutes=10) if submitted else None,
                datetime.now(UTC) if finalized else None,
            ),
        )
    return return_id


async def _insert_inspection_run(
    db: Database,
    org: str,
    return_id: str,
    *,
    kind: str = "judgment",
    status: str = "completed",
    api_requests: int = 1,
    tool_calls: int = 0,
    latency_ms: int | None = 1000,
    cost_usd_micros: int | None = None,
    completed_at: datetime | None = None,
    validation_report: dict[str, object] | None = None,
) -> str:
    inspection_id = _fresh_id("ins-obs")
    completed_at = completed_at or (datetime.now(UTC) if status == "completed" else None)
    async with db.transaction(org) as conn:
        await conn.execute(
            "INSERT INTO rm.inspection_runs (inspection_id, org_id, return_id, kind, status, "
            "api_requests, tool_calls, latency_ms, cost_usd_micros, completed_at, "
            "validation_report) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
            (
                inspection_id,
                org,
                return_id,
                kind,
                status,
                api_requests,
                tool_calls,
                latency_ms,
                cost_usd_micros,
                completed_at,
                _json(validation_report) if validation_report is not None else None,
            ),
        )
    return inspection_id


async def _insert_inspection_result(
    db: Database,
    org: str,
    return_id: str,
    inspection_id: str,
    *,
    identity_match: str = "yes",
    completeness_status: str = "complete",
    recommended_disposition: str | None = "restock",
    disposition_extra: dict[str, object] | None = None,
    review_reasons: list[str] | None = None,
) -> None:
    result_id = _fresh_id("res-obs")
    disposition: dict[str, object] = {
        "recommended_disposition": recommended_disposition,
        "no_recommendation_reason": None if recommended_disposition else "rule_gap",
        "currency": "INR",
    }
    if disposition_extra:
        disposition.update(disposition_extra)
    requires_review = recommended_disposition is None
    async with db.transaction(org) as conn:
        await conn.execute(
            "INSERT INTO rm.inspection_results (result_id, org_id, return_id, inspection_id, "
            "identity_match, fused_identity, unit_presence, completeness_status, components, "
            "cosmetic_grade, amazon_condition, listing_blockers, condition, model_observed_state, "
            "claim_signals, uncertainties, retake_requests, validator_actions, checks, "
            "escalation_state, recommended_disposition, no_recommendation_reason, provisional, "
            "relistable_as_is, disposition, disposition_inputs, requires_review, review_reasons, "
            "requires_signoff) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, "
            "%s, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, "
            "%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)",
            (
                result_id,
                org,
                return_id,
                inspection_id,
                identity_match,
                "{}",
                "present",
                completeness_status,
                "[]",
                None,
                "Used - Good",
                [],
                "{}",
                None,
                "{}",
                "[]",
                "[]",
                "[]",
                "[]",
                "not_triggered",
                recommended_disposition,
                disposition["no_recommendation_reason"],
                False,
                True,
                _json(disposition),
                "{}",
                requires_review or bool(review_reasons),
                review_reasons or [],
                False,
            ),
        )


def _json(d: dict[str, object]) -> str:
    import json

    return json.dumps(d)


# ── T-OBS-03: fresh org -> every metric is "no data" ────────────────────────────


@pytest.mark.asyncio
async def test_t_obs_03_summary_no_data_on_fresh_org(db: Database, obs_org: str) -> None:
    async with db.transaction(obs_org) as conn:
        summary = await MetricsService(conn, obs_org).summary("all")
    assert summary, "summary must not be empty"
    for name, envelope in summary.items():
        assert envelope["n"] == 0, f"{name} should have n=0 on a brand-new org"
        assert envelope["value"] == "no data", f"{name} should render 'no data', not {envelope['value']!r}"


# ── T-OBS-04: real throughput / requests / latency ──────────────────────────────


@pytest.mark.asyncio
async def test_t_obs_04_real_counts_and_latency(db: Database, obs_org: str) -> None:
    r1 = await _make_return(db, obs_org, submitted=True, finalized=True)
    r2 = await _make_return(db, obs_org, submitted=True, finalized=True)
    await _insert_inspection_run(db, obs_org, r1, api_requests=1, tool_calls=0, latency_ms=1000)
    await _insert_inspection_run(db, obs_org, r2, api_requests=2, tool_calls=1, latency_ms=3000)

    async with db.transaction(obs_org) as conn:
        service = MetricsService(conn, obs_org)
        throughput = await service.throughput_per_hour("all")
        requests = await service.requests_per_inspection("all")
        tool_calls = await service.tool_calls_per_inspection("all")
        latency = await service.model_latency_ms("all")

    assert throughput.n == 2
    assert requests.n == 2
    assert requests.value["mean"] == pytest.approx(1.5)
    assert tool_calls.value == pytest.approx(0.5)
    assert latency.n == 2
    assert latency.value["mean_ms"] == pytest.approx(2000)


@pytest.mark.asyncio
async def test_t_obs_04b_capture_to_decision_latency(db: Database, obs_org: str) -> None:
    return_id = await _make_return(db, obs_org, submitted=True, finalized=True)
    async with db.transaction(obs_org) as conn:
        cur = await conn.execute(
            "SELECT submitted_at FROM rm.returns WHERE org_id = %s AND return_id = %s",
            (obs_org, return_id),
        )
        row = await cur.fetchone()
    submitted_at = row["submitted_at"]
    completed_at = submitted_at + timedelta(seconds=5)
    await _insert_inspection_run(db, obs_org, return_id, completed_at=completed_at)

    async with db.transaction(obs_org) as conn:
        result = await MetricsService(conn, obs_org).capture_to_decision_ms("all")
    assert result.n == 1
    assert result.value["mean_ms"] == pytest.approx(5000, abs=50)


# ── T-OBS-05: rates and distributions over a real mixed population ─────────────


@pytest.mark.asyncio
async def test_t_obs_05_uncertain_rate_and_distribution(db: Database, obs_org: str) -> None:
    r1 = await _make_return(db, obs_org, submitted=True, finalized=True)
    r2 = await _make_return(db, obs_org, submitted=True, finalized=True)
    ins1 = await _insert_inspection_run(
        db, obs_org, r1, validation_report={"invented_reference_count": 2, "invented_quote_count": 1}
    )
    ins2 = await _insert_inspection_run(
        db, obs_org, r2, validation_report={"invented_reference_count": 0, "invented_quote_count": 0}
    )
    await _insert_inspection_result(
        db,
        obs_org,
        r1,
        ins1,
        identity_match="yes",
        recommended_disposition="restock",
        review_reasons=["possible_reused_photo"],
    )
    await _insert_inspection_result(
        db, obs_org, r2, ins2, identity_match="uncertain", recommended_disposition="liquidate"
    )

    async with db.transaction(obs_org) as conn:
        service = MetricsService(conn, obs_org)
        uncertain = await service.uncertain_rate("all")
        dist = await service.disposition_distribution("all")
        integrity = await service.integrity_counters("all")

    assert uncertain.n == 2
    assert uncertain.value == pytest.approx(0.5)
    assert dist.n == 2
    assert dist.value == {"restock": 0.5, "liquidate": 0.5}
    assert integrity.n == 2
    assert integrity.value["invented_reference_count"] == 2
    assert integrity.value["invented_quote_count"] == 1
    assert integrity.value["reused_photo_flag_count"] == 1
    assert integrity.value["injection_flag_count"] == 0


# ── T-OBS-06: economics cost conversion against the real fx.yaml rate ──────────


@pytest.mark.asyncio
async def test_t_obs_06_cost_by_stage_and_per_inspection(db: Database, obs_org: str) -> None:
    r1 = await _make_return(db, obs_org, submitted=True, finalized=True)
    r2 = await _make_return(db, obs_org, submitted=True, finalized=True)
    # 1,000,000 micros = $1.00 exactly, so the arithmetic is easy to check by hand.
    await _insert_inspection_run(db, obs_org, r1, cost_usd_micros=1_000_000)
    await _insert_inspection_run(db, obs_org, r2, cost_usd_micros=2_000_000)

    from returns_manager.config import get_settings

    async with db.transaction(obs_org) as conn:
        econ = EconomicsService(conn, obs_org, get_settings())
        by_stage = await econ.cost_by_stage("all")
        per_inspection = await econ.cost_per_inspection("all")

    judgment = by_stage["judgment"]
    assert judgment["n"] == 2
    assert judgment["value"]["mean_usd"] == pytest.approx(1.5)
    fx = load_fx()
    assert judgment["value"]["mean_inr"] == pytest.approx(float(usd_to_inr(Decimal("1.5"), fx)))
    # No escalation/audit rows -> the blended per-inspection cost is just judgment's mean.
    assert per_inspection["value"]["mean_usd"] == pytest.approx(1.5)


# ── T-OBS-07: recovery uplift from a real disposition-engine-shaped record ─────


@pytest.mark.asyncio
async def test_t_obs_07_recovery_uplift_is_synthetic_and_computed(db: Database, obs_org: str) -> None:
    return_id = await _make_return(db, obs_org, submitted=True, finalized=True)
    inspection_id = await _insert_inspection_run(db, obs_org, return_id)
    # Mirrors disposition/engine.py's DispositionDecision.expected_recovery_minor shape:
    # a list of [route, minor_amount] pairs, as it is actually persisted (dataclasses.asdict
    # + json.dumps of a tuple-of-tuples becomes a JSON array of 2-element arrays).
    await _insert_inspection_result(
        db,
        obs_org,
        return_id,
        inspection_id,
        recommended_disposition="refurbish",
        disposition_extra={
            "expected_recovery_minor": [
                ["restock_new", 10000],
                ["restock_used", 8000],
                ["refurbish", 6000],
                ["liquidate", 2000],
            ]
        },
    )

    from returns_manager.config import get_settings

    async with db.transaction(obs_org) as conn:
        uplift = await EconomicsService(conn, obs_org, get_settings()).recovery_uplift("all")

    assert uplift["n"] == 1
    assert uplift["value"]["synthetic"] is True
    assert uplift["value"]["currency"] == "INR"
    assert uplift["value"]["uplift_total_minor"] == 6000 - 2000
    assert uplift["value"]["baseline_policy"] == "liquidate all opened returns"


# ── T-OBS-08: spend guard (pure; no DB) ─────────────────────────────────────────


def _budget_status(*, used: int, budget: int) -> object:
    from returns_manager.jobs.budget import BudgetStatus

    return BudgetStatus(
        model_id="gemini-3.8-flash",
        quota_day=datetime.now(UTC).date(),
        requests_used=used,
        daily_budget=budget,
        requests_remaining=max(budget - used, 0),
        allowed=used < budget,
        next_reset_utc=datetime.now(UTC) + timedelta(hours=6),
    )


def test_t_obs_08a_quota_days_guard() -> None:
    from returns_manager.errors import SpendGuardRefused

    status = _budget_status(used=10, budget=18)  # 8 remaining today
    # 5 units at ~1 request each fits comfortably within today's remaining budget.
    result = preflight_bulk_spend(
        model_id="gemini-3.8-flash",
        units=5,
        expected_requests_per_unit=1.2,
        estimated_cost_usd_per_unit=Decimal("0.001"),
        budget_status=status,
        spend_cap_usd=Decimal("0"),
    )
    assert result.days_needed == 1
    assert result.requests_needed == 6

    # 50 units needs far more than 8 remaining requests -> multiple days -> refused.
    with pytest.raises(SpendGuardRefused):
        preflight_bulk_spend(
            model_id="gemini-3.8-flash",
            units=50,
            expected_requests_per_unit=1.2,
            estimated_cost_usd_per_unit=Decimal("0.001"),
            budget_status=status,
            spend_cap_usd=Decimal("0"),
        )

    # The same run succeeds once the human passes --allow-multi-day.
    result = preflight_bulk_spend(
        model_id="gemini-3.8-flash",
        units=50,
        expected_requests_per_unit=1.2,
        estimated_cost_usd_per_unit=Decimal("0.001"),
        budget_status=status,
        spend_cap_usd=Decimal("0"),
        allow_multi_day=True,
    )
    assert result.days_needed > 1


def test_t_obs_08b_spend_cap_guard() -> None:
    from returns_manager.errors import SpendGuardRefused

    status = _budget_status(used=0, budget=100)
    with pytest.raises(SpendGuardRefused):
        preflight_bulk_spend(
            model_id="gemini-3.8-flash",
            units=100,
            expected_requests_per_unit=1.0,
            estimated_cost_usd_per_unit=Decimal("1.00"),  # $100 total > $10 cap
            budget_status=status,
            spend_cap_usd=Decimal("10"),
        )

    result = preflight_bulk_spend(
        model_id="gemini-3.8-flash",
        units=100,
        expected_requests_per_unit=1.0,
        estimated_cost_usd_per_unit=Decimal("1.00"),
        budget_status=status,
        spend_cap_usd=Decimal("10"),
        confirm_spend=True,
    )
    assert result.estimated_cost_usd == Decimal("100.0000")
