"""Load and resilience unit tests (§19 "Load", §20 `load-test`, §23 P13 acceptance).

Tests T-LOD-01 through T-LOD-10:
- CLI options and usage
- Latency profile parsing and sampling
- Percentiles calculation (p50, p90, p95, p99)
- Replay load test with zero duplicates and zero drops
- Injected outage fail-open guarantee
- Spend guard preflight refusal in live mode (exit 4)
- Burst scenario drill
- Kill-switch drill
- Circuit breaker drill
- Budget exhaustion drill
"""

from __future__ import annotations

from typing import Any

import pytest

from returns_manager.cli import main as cli_main
from returns_manager.config import get_settings
from returns_manager.db.pool import Database
from returns_manager.errors import BadRequest, SpendGuardRefused
from returns_manager.load.drills import (
    run_budget_exhaustion_drill,
    run_burst_scenario,
    run_circuit_breaker_drill,
    run_kill_switch_drill,
    run_outage_drill,
)
from returns_manager.load.models import (
    LatencyPercentiles,
    LoadMode,
)
from returns_manager.load.profiles import parse_latency_profile
from returns_manager.load.runner import generate_test_jpeg, run_load_test

# ── Pure tests: CLI, profiles, math ──────────────────────────────────────────


def test_t_lod_01_cli_help_and_exit_code() -> None:
    """CLI load-test command is registered and outputs help with code 0."""
    code = cli_main.run(["load-test", "--help"])
    assert code == 0


def test_t_lod_02_latency_profile_parser() -> None:
    """Parse various latency profile specifications."""
    p_inst = parse_latency_profile("instant")
    assert p_inst.kind == "instant"
    assert p_inst.sample_delay_s() == 0.0

    p_zero = parse_latency_profile("0")
    assert p_zero.kind == "instant"
    assert p_zero.sample_delay_s() == 0.0

    p_none = parse_latency_profile(None)
    assert p_none.kind == "instant"

    p_fixed = parse_latency_profile("fixed:50ms")
    assert p_fixed.kind == "fixed"
    assert p_fixed.fixed_ms == 50.0
    assert p_fixed.sample_delay_s() == 0.05

    p_fixed_s = parse_latency_profile("fixed:0.2s")
    assert p_fixed_s.kind == "fixed"
    assert p_fixed_s.fixed_ms == 200.0
    assert p_fixed_s.sample_delay_s() == 0.2

    p_uniform = parse_latency_profile("uniform:10ms:50ms")
    assert p_uniform.kind == "uniform"
    assert p_uniform.min_ms == 10.0
    assert p_uniform.max_ms == 50.0
    for _ in range(50):
        delay = p_uniform.sample_delay_s()
        assert 0.010 <= delay <= 0.050

    p_bare = parse_latency_profile("100ms")
    assert p_bare.kind == "fixed"
    assert p_bare.fixed_ms == 100.0

    with pytest.raises(BadRequest):
        parse_latency_profile("fixed:-10ms")

    with pytest.raises(BadRequest):
        parse_latency_profile("uniform:50ms:10ms")

    with pytest.raises(BadRequest):
        parse_latency_profile("invalid:format:xyz")


def test_t_lod_03_percentiles_calculation() -> None:
    """Calculate p50, p90, p95, p99, mean, min, and max accurately."""
    values = [float(i) for i in range(1, 101)]  # 1 to 100
    p = LatencyPercentiles.compute(values)
    assert p.p50_ms == 50.5
    assert p.p90_ms == 90.1
    assert p.p95_ms == 95.05
    assert p.p99_ms == 99.01
    assert p.min_ms == 1.0
    assert p.max_ms == 100.0
    assert p.mean_ms == 50.5

    # Empty list edge case
    p_empty = LatencyPercentiles.compute([])
    assert p_empty.p50_ms == 0.0
    assert p_empty.mean_ms == 0.0


def test_t_lod_04_test_jpeg_generator() -> None:
    """Generate textured JPEG bytes that pass size and decode checks."""
    data = generate_test_jpeg(42, (300, 200))
    assert len(data) > 1000
    assert data[:2] == b"\xff\xd8"  # JPEG SOI marker


# ── DB tests: Replay load test, drills, spend guard ──────────────────────────


@pytest.mark.db
async def test_t_lod_05_replay_mode_throughput_and_zero_duplicates(
    db: Database, quiet_queue: set[str]
) -> None:
    """Replay mode measures system throughput, verifies zero duplicates and zero drops (§23)."""
    settings = get_settings()
    n_units = 8
    concurrency = 3

    report = await run_load_test(
        db,
        settings,
        mode="replay",
        units=n_units,
        concurrency=concurrency,
        latency_profile="instant",
        timeout_s=30.0,
    )

    assert report.mode == LoadMode.REPLAY
    assert report.units_requested == n_units
    assert report.units_completed == n_units
    assert report.units_pending == 0
    assert report.units_needs_attention == 0
    assert report.zero_duplicates_verified, "zero duplicates must be verified"
    assert report.zero_drops_verified, "zero drops must be verified"
    assert report.throughput_units_per_s > 0.0
    assert report.latency.p50_ms >= 0.0
    assert report.latency.p95_ms >= 0.0
    assert report.latency.p99_ms >= 0.0

    md = report.to_markdown()
    assert "Load and Resilience Test Report (§23)" in md
    assert "**Zero Duplicates:** PASS (0 duplicates)" in md
    assert "**Zero Drops:** PASS (0 drops)" in md


@pytest.mark.db
async def test_t_lod_06_simulated_latency_profile_distribution(db: Database, quiet_queue: set[str]) -> None:
    """Simulated latency profile reflects in measured duration percentiles."""
    settings = get_settings()
    n_units = 4
    concurrency = 2

    # Fixed 30ms profile
    report = await run_load_test(
        db,
        settings,
        mode="replay",
        units=n_units,
        concurrency=concurrency,
        latency_profile="fixed:30ms",
        timeout_s=30.0,
    )

    assert report.units_completed == n_units
    assert report.zero_duplicates_verified
    assert report.zero_drops_verified
    # Mean total latency should be at least ~30ms due to simulated delay
    assert report.latency.mean_ms >= 25.0


@pytest.mark.db
async def test_t_lod_07_live_mode_spend_guard_refuses_without_confirm(
    db: Database,
) -> None:
    """Live mode must run through P11 spend guard and refuse without --confirm-spend (§18.4, §20)."""
    settings = get_settings()

    with pytest.raises(SpendGuardRefused):
        await run_load_test(
            db,
            settings,
            mode="live",
            units=5,
            concurrency=2,
            confirm_spend=False,
        )


@pytest.mark.db
async def test_t_lod_08_injected_outage_fails_open(db: Database, quiet_queue: set[str]) -> None:
    """Fail-open under an injected provider outage: photos intact, return pending/needs_attention (§23)."""
    settings = get_settings()
    n_units = 5
    concurrency = 2

    report = await run_load_test(
        db,
        settings,
        mode="replay",
        units=n_units,
        concurrency=concurrency,
        injected_outage="provider_500",
        timeout_s=20.0,
    )

    assert report.zero_duplicates_verified
    assert report.zero_drops_verified
    assert report.fail_open_verified, "must fail open with photos intact and no auto-disposition"
    assert report.units_completed == 0
    # All units must be in pending (retryable) or needs_attention
    assert report.units_pending + report.units_needs_attention == n_units


@pytest.mark.db
async def test_t_lod_09_resilience_drills_suite(db: Database, quiet_queue: set[str]) -> None:
    """Resilience drills: burst scenario, outage drill, kill-switch, circuit breaker, budget."""
    settings = get_settings()

    # 1. Burst scenario drill
    burst_rep = await run_burst_scenario(db, settings, n_units=8, concurrency=3)
    assert burst_rep.passed, f"burst drill failed: {burst_rep.details}"
    assert burst_rep.details["zero_duplicates"] is True
    assert burst_rep.details["zero_drops"] is True

    # 2. Injected outage drill
    outage_rep = await run_outage_drill(db, settings, n_units=4, concurrency=2)
    assert outage_rep.passed, f"outage drill failed: {outage_rep.details}"
    assert outage_rep.details["fail_open_verified"] is True

    # 3. Kill-switch drill
    kill_rep = await run_kill_switch_drill(db, settings)
    assert kill_rep.passed, f"kill-switch drill failed: {kill_rep.details}"
    assert kill_rep.details["held_pending"] is True
    assert kill_rep.details["attempts_not_spent"] is True
    assert kill_rep.details["resumed_and_succeeded"] is True

    # 4. Circuit breaker drill
    circuit_rep = await run_circuit_breaker_drill(db, settings)
    assert circuit_rep.passed, f"circuit breaker drill failed: {circuit_rep.details}"
    assert circuit_rep.details["tripped_open"] is True
    assert circuit_rep.details["recovered_closed"] is True

    # 5. Budget exhaustion drill
    budget_rep = await run_budget_exhaustion_drill(db, settings)
    assert budget_rep.passed, f"budget drill failed: {budget_rep.details}"
    assert budget_rep.details["quota_denied_when_budget_exhausted"] is True


def test_t_lod_10_cli_load_test_json_export(tmp_path: Any) -> None:
    """CLI load-test command with --out writes valid JSON report."""
    out_file = tmp_path / "load_report.json"
    code = cli_main.run(
        [
            "load-test",
            "--mode",
            "replay",
            "--units",
            "3",
            "--concurrency",
            "2",
            "--latency-profile",
            "instant",
            "--out",
            str(out_file),
        ]
    )
    assert code == 0
    assert out_file.exists()
    import json

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["mode"] == "replay"
    assert data["units_requested"] == 3
    assert data["units_completed"] == 3
    assert data["zero_duplicates_verified"] is True
    assert data["zero_drops_verified"] is True
    assert "latency_ms" in data
    assert "p50_ms" in data["latency_ms"]
