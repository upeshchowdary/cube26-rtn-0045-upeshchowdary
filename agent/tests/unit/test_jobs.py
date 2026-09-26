"""Durable jobs, worker and fail-open (§10, §19 T-Q-*, T-FO-*; phase P4 acceptance).

Pure tests (state machines, backoff, circuit, error classes, keys, priority) need nothing. The `db` tests
need the local Supabase stack. The worker claims jobs across ALL orgs, so each worker test runs inside
`quiet_queue`: every job that is not this test's is parked (made not-yet-due) through the privileged
migrator connection and restored exactly afterwards.
"""

from __future__ import annotations

import asyncio
import io
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest
from PIL import Image

from returns_manager.config import Settings, get_settings
from returns_manager.db.pool import Database
from returns_manager.errors import (
    CircuitOpenError,
    ConfigError,
    HandlerNotConfigured,
    InvalidTransitionError,
    QuotaExhaustedError,
)
from returns_manager.ids import new_id
from returns_manager.intake.service import IntakeService
from returns_manager.jobs import service as jobs_svc
from returns_manager.jobs.budget import (
    check_and_reserve_budget,
    get_budget_status,
    get_next_pacific_reset,
    get_pacific_quota_day,
    release_budget,
)
from returns_manager.jobs.circuit import CircuitBreaker, CircuitState
from returns_manager.jobs.queue import (
    JobQueue,
    JobRecord,
    compute_inspection_idempotency_key,
    compute_job_priority,
)
from returns_manager.jobs.retry import classify_error, compute_next_attempt_at
from returns_manager.jobs.statemachine import (
    JobStatus,
    ReturnStatus,
    transition_job_status,
    transition_return_status,
)
from returns_manager.jobs.worker import HandlerResult, Worker, assert_lease_sizing
from returns_manager.security import controls
from returns_manager.security.roles import Principal, Role

# ── pure: state machines ───────────────────────────────────────────────────


def test_t_q_01_state_machines_allow_and_refuse() -> None:
    assert transition_return_status("capturing", "queued") == ReturnStatus.QUEUED
    assert transition_return_status("inspecting", "pending") == ReturnStatus.PENDING
    assert transition_return_status("needs_attention", "queued") == ReturnStatus.QUEUED
    assert transition_job_status("failed_retryable", "in_progress") == JobStatus.IN_PROGRESS
    for cur, target in [("finalized", "queued"), ("capturing", "finalized"), ("queued", "awaiting_operator")]:
        with pytest.raises(InvalidTransitionError):
            transition_return_status(cur, target)
    for jcur, jtarget in [("succeeded", "pending"), ("cancelled", "in_progress"), ("pending", "succeeded")]:
        with pytest.raises(InvalidTransitionError):
            transition_job_status(jcur, jtarget)


# ── pure: backoff, circuit, error classes ──────────────────────────────────


def test_t_q_02_backoff_schedule_is_capped_and_jittered() -> None:
    now = datetime(2026, 9, 25, tzinfo=UTC)
    for attempts, base in [(0, 5), (1, 10), (3, 40), (6, 300), (20, 300)]:
        for jitter in (0.8, 1.0, 1.2):
            delay = (compute_next_attempt_at(attempts, jitter_factor=jitter, now=now) - now).total_seconds()
            assert delay == pytest.approx(base * jitter)
    for _ in range(200):
        delay = (compute_next_attempt_at(4, now=now) - now).total_seconds()
        assert 80 * 0.8 <= delay <= 80 * 1.2


def test_t_q_03_circuit_opens_half_opens_and_closes() -> None:
    t0 = datetime(2026, 9, 25, tzinfo=UTC)
    cb = CircuitBreaker("m", failure_threshold=3, cooldown_s=60)
    cb.record_failure(counts_toward_circuit=False, now=t0)  # non-circuit errors never count
    for _ in range(2):
        cb.record_failure(now=t0)
    assert cb.state == CircuitState.CLOSED
    cb.record_failure(now=t0)
    assert cb.state == CircuitState.OPEN
    assert not cb.allow_request(now=t0 + timedelta(seconds=59))
    assert cb.allow_request(now=t0 + timedelta(seconds=61))  # one half-open probe
    assert cb.state == CircuitState.HALF_OPEN
    assert not cb.allow_request(now=t0 + timedelta(seconds=62))  # only one probe at a time
    cb.record_failure(now=t0 + timedelta(seconds=63))  # probe failed → open again
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request(now=t0 + timedelta(seconds=124))
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request(now=t0 + timedelta(seconds=125))


@pytest.mark.parametrize(
    ("exc", "error_class", "retryable", "counts"),
    [
        (HandlerNotConfigured("no handler"), "configuration", False, False),
        (ConfigError("bad config"), "configuration", False, False),
        (InvalidTransitionError("return", "finalized", "queued"), "invalid_state", False, False),
        (QuotaExhaustedError("daily budget used"), "quota_exhausted", False, False),
        (CircuitOpenError("open"), "circuit_open", True, False),
        (TimeoutError("read timed out"), "timeout", True, True),
        (ConnectionError("reset by peer"), "network", True, True),
        (
            RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded for requests per day"),
            "quota_exhausted",
            False,
            False,
        ),
        (RuntimeError("429 rate limit: requests per minute"), "rate_limit", True, True),
        (RuntimeError("503 model overloaded"), "server_error", True, True),
        (KeyError("oops"), "unexpected_error", True, False),
    ],
)
def test_t_q_04_error_classification(exc: Exception, error_class: str, retryable: bool, counts: bool) -> None:
    c = classify_error(exc)
    assert (c.error_class, c.retryable, c.counts_toward_circuit) == (error_class, retryable, counts)


def test_t_q_05_idempotency_key_is_deterministic_and_kind_specific() -> None:
    a = compute_inspection_idempotency_key("org_a", "r1", ["b" * 64, "a" * 64])
    assert a == compute_inspection_idempotency_key("org_a", "r1", ["a" * 64, "b" * 64])  # order-free
    assert a != compute_inspection_idempotency_key("org_a", "r1", ["a" * 64, "c" * 64])  # photos change it
    assert a != compute_inspection_idempotency_key("org_a", "r1", ["a" * 64, "b" * 64], kind="escalation")
    assert a != compute_inspection_idempotency_key("org_b", "r1", ["a" * 64, "b" * 64])


def test_t_q_06_priority_rules() -> None:
    assert compute_job_priority() == 0
    assert compute_job_priority(item_value_minor=500000) == 20
    assert compute_job_priority(item_value_minor=499999) == 0
    assert compute_job_priority(observed_state="empty_box") == 30
    assert compute_job_priority(observed_state="damaged", item_value_minor=900000) == 50
    assert compute_job_priority(kind="escalation") == 10


def test_t_q_07_lease_sizing_is_asserted() -> None:
    s = get_settings().model_copy(
        update={"rm_model_timeout_s": 300, "rm_max_round_trips": 2, "rm_job_lease_s": 600}
    )
    with pytest.raises(ConfigError):
        assert_lease_sizing(s)


def test_t_q_08_pacific_quota_day_and_reset() -> None:
    # 2026-09-25 06:00 UTC is still 2026-09-24 in Los Angeles (UTC-7); the reset is 07:00 UTC.
    t = datetime(2026, 9, 25, 6, 0, tzinfo=UTC)
    assert str(get_pacific_quota_day(now_utc=t)) == "2026-09-24"
    assert get_next_pacific_reset(now_utc=t) == datetime(2026, 9, 25, 7, 0, tzinfo=UTC)


# ── db fixtures and helpers ────────────────────────────────────────────────


def _fresh_org() -> str:
    return f"org_t{uuid.uuid4().hex[:12]}"


def _jpeg(seed: int) -> bytes:
    """A sharp, well-exposed, textured photo (passes the quality gate); different seeds look different."""
    rng = np.random.default_rng(seed)
    blocks = rng.integers(60, 190, size=(18, 24, 3), dtype=np.uint8)
    arr = np.kron(blocks, np.ones((50, 50, 1), dtype=np.uint8))
    buf = io.BytesIO()
    Image.fromarray(arr, mode="RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _settings(**overrides: Any) -> Settings:
    base = {
        "rm_judgment_model": f"test-model-{uuid.uuid4().hex[:8]}",
        "rm_daily_request_budget_judgment": 100,
    }
    base.update(overrides)
    return get_settings().model_copy(update=base)


async def _new_org(db: Database) -> str:
    org = _fresh_org()
    async with db.transaction(org) as conn:
        await conn.execute("INSERT INTO rm.organizations (org_id, name) VALUES (%s, 'jobs test')", (org,))
    return org


async def _queued_return(db: Database, org: str, n: int = 1) -> tuple[str, JobRecord]:
    svc = IntakeService(db)
    ret = await svc.create_return(org_id=org, actor_id="op", order_id=f"ORD-{n}", unit_id=f"UNIT-{n:04d}")
    await svc.upload_photo(org_id=org, actor_id="op", return_id=ret.return_id, photo_bytes=_jpeg(40 + n))
    async with db.transaction(org) as conn:
        job = await JobQueue.enqueue_job(conn, org, ret.return_id, idempotency_key=f"t-{new_id()}")
    return ret.return_id, job


async def _job(db: Database, org: str, job_id: str) -> JobRecord:
    async with db.transaction(org) as conn:
        job = await JobQueue.get_job(conn, org, job_id)
    assert job is not None
    return job


async def _return_status(db: Database, org: str, return_id: str) -> str:
    async with db.transaction(org) as conn:
        cur = await conn.execute("SELECT status FROM rm.returns WHERE return_id = %s", (return_id,))
        row = await cur.fetchone()
    assert row is not None
    return str(row["status"])


async def _photo_count(db: Database, org: str, return_id: str) -> int:
    async with db.transaction(org) as conn:
        cur = await conn.execute(
            "SELECT count(*) AS n FROM rm.return_photos WHERE return_id = %s", (return_id,)
        )
        row = await cur.fetchone()
    assert row is not None
    return int(row["n"])


def _ok_handler(calls: list[str], delay_s: float = 0.0) -> Any:
    async def handler(job: JobRecord) -> HandlerResult:
        calls.append(job.job_id)
        if delay_s:
            await asyncio.sleep(delay_s)
        return HandlerResult(target_return_status=ReturnStatus.AWAITING_OPERATOR)

    return handler


# ── db: queue ──────────────────────────────────────────────────────────────


@pytest.mark.db
async def test_t_q_09_every_job_processed_exactly_once(db: Database, quiet_queue: set[str]) -> None:
    orgs = [await _new_org(db), await _new_org(db)]
    jobs: dict[str, tuple[str, str]] = {}
    for i in range(12):
        org = orgs[i % 2]
        return_id, job = await _queued_return(db, org, i + 1)
        jobs[job.job_id] = (org, return_id)

    calls: list[str] = []
    settings = _settings(rm_max_inflight_per_org=4)
    workers = [Worker(db, settings, concurrency=2, handler=_ok_handler(calls, 0.05)) for _ in range(3)]
    runs = [asyncio.create_task(w.run()) for w in workers]
    try:
        for _ in range(200):
            if len(set(calls) & set(jobs)) == len(jobs):
                break
            await asyncio.sleep(0.1)
    finally:
        for w in workers:
            await w.stop()
        await asyncio.gather(*runs)

    counts = Counter(c for c in calls if c in jobs)
    assert set(counts) == set(jobs), "every job must be processed"
    assert max(counts.values()) == 1, f"a job was processed twice: {counts.most_common(3)}"
    assert not set(calls) - set(jobs), "the worker processed a job that is not this test's"
    for job_id, (org, return_id) in jobs.items():
        assert (await _job(db, org, job_id)).status == JobStatus.SUCCEEDED
        assert await _return_status(db, org, return_id) == "awaiting_operator"


@pytest.mark.db
async def test_t_q_10_expired_lease_is_reclaimed(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    _, job = await _queued_return(db, org)
    async with db.transaction(None) as conn:
        first = await JobQueue.claim_next_job(conn, "dead-worker", lease_s=1, max_inflight_per_org=4)
    assert first is not None
    assert first.job_id == job.job_id
    assert first.attempts == 1
    await asyncio.sleep(1.5)  # the "dead" worker never renews
    async with db.transaction(None) as conn:
        second = await JobQueue.claim_next_job(conn, "live-worker", lease_s=60, max_inflight_per_org=4)
    assert second is not None
    assert second.job_id == job.job_id
    assert second.lease_owner == "live-worker"
    assert second.attempts == 2


@pytest.mark.db
async def test_t_q_11_per_org_inflight_cap(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    await _queued_return(db, org, 1)
    await _queued_return(db, org, 2)
    async with db.transaction(None) as conn:
        a = await JobQueue.claim_next_job(conn, "w1", lease_s=60, max_inflight_per_org=1)
        b = await JobQueue.claim_next_job(conn, "w2", lease_s=60, max_inflight_per_org=1)
        c = await JobQueue.claim_next_job(conn, "w3", lease_s=60, max_inflight_per_org=2)
    assert a is not None
    assert b is None, "the org is at its in-flight cap"
    assert c is not None
    assert c.job_id != a.job_id


@pytest.mark.db
async def test_t_q_12_kill_switch_holds_without_spending_attempts(
    db: Database, quiet_queue: set[str]
) -> None:
    """Global OFF + org ON is OFF (effective = global AND org); the job waits, the return stays queued."""
    org = await _new_org(db)
    return_id, job = await _queued_return(db, org)
    admin = Principal(kind="user", org_id=org, actor_id="t", role=Role.ADMIN)
    await controls.set_org_control(db, admin, controls.Control.MODEL_CALLS, True, "drill: org on")
    await controls.set_global_control(db, controls.Control.MODEL_CALLS, False, "drill: global off", "test")
    calls: list[str] = []
    try:
        worker = Worker(db, _settings(), concurrency=1, handler=_ok_handler(calls))
        task = asyncio.create_task(worker.run())
        await asyncio.sleep(1.5)
        await worker.stop()
        await task
    finally:
        await controls.set_global_control(db, controls.Control.MODEL_CALLS, True, "drill done", "test")
    held = await _job(db, org, job.job_id)
    assert calls == [], "no handler call while model calls are off"
    assert held.status == JobStatus.FAILED_RETRYABLE
    assert held.last_error_class == "model_calls_disabled"
    assert held.attempts == 0, "a hold must not spend an attempt"
    assert held.next_attempt_at > datetime.now(UTC)
    assert await _return_status(db, org, return_id) == "queued"


@pytest.mark.db
async def test_t_q_13_quota_exhausted_holds_until_reset(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    return_id, job = await _queued_return(db, org)
    settings = _settings(rm_daily_request_budget_judgment=0)
    calls: list[str] = []
    worker = Worker(db, settings, concurrency=1, handler=_ok_handler(calls))
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(1.0)
    await worker.stop()
    await task
    held = await _job(db, org, job.job_id)
    assert calls == []
    assert held.last_error_class == "quota_exhausted"
    assert held.attempts == 0
    assert abs((held.next_attempt_at - get_next_pacific_reset()).total_seconds()) < 5
    assert await _return_status(db, org, return_id) == "queued"


@pytest.mark.db
async def test_t_q_14_budget_never_exceeded_under_concurrency(db: Database) -> None:
    model = f"test-budget-{uuid.uuid4().hex[:8]}"

    async def reserve() -> bool:
        async with db.transaction(None) as conn:
            status = await check_and_reserve_budget(conn, model, daily_budget=5, count=2)
            await asyncio.sleep(0.02)
            return status.allowed

    allowed = await asyncio.gather(*[reserve() for _ in range(10)])
    assert sum(allowed) == 2, "5 requests fit two reservations of 2, never three"
    async with db.transaction(None) as conn:
        await release_budget(conn, model, 1)
        status = await get_budget_status(conn, model, daily_budget=5)
    assert status.requests_used == 3
    assert status.requests_remaining == 2


@pytest.mark.db
async def test_t_q_15_run_max_jobs_returns_count(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    for i in range(3):
        await _queued_return(db, org, i + 1)
    calls: list[str] = []
    worker = Worker(db, _settings(), concurrency=2, handler=_ok_handler(calls))
    finished = await asyncio.wait_for(worker.run(max_jobs=3), timeout=20)
    assert finished == 3
    assert len(calls) == 3


@pytest.mark.db
async def test_t_q_16_graceful_shutdown_releases_the_lease(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    return_id, job = await _queued_return(db, org)
    calls: list[str] = []
    worker = Worker(db, _settings(), concurrency=1, handler=_ok_handler(calls, delay_s=30))
    task = asyncio.create_task(worker.run())
    for _ in range(50):
        if calls:
            break
        await asyncio.sleep(0.1)
    await worker.stop(grace_period_s=0.3)
    await task
    released = await _job(db, org, job.job_id)
    assert released.status == JobStatus.FAILED_RETRYABLE
    assert released.last_error_class == "shutdown"
    assert released.lease_owner is None
    assert await _return_status(db, org, return_id) == "inspecting"  # visible, not decided
    assert await _photo_count(db, org, return_id) == 1


@pytest.mark.db
async def test_t_q_17_stale_job_is_cancelled(db: Database, quiet_queue: set[str]) -> None:
    """A retake sent the return back to capturing after submit: the old job must not inspect it."""
    org = await _new_org(db)
    return_id, job = await _queued_return(db, org)
    async with db.transaction(org) as conn:
        await conn.execute("UPDATE rm.returns SET status = 'capturing' WHERE return_id = %s", (return_id,))
    calls: list[str] = []
    worker = Worker(db, _settings(), concurrency=1, handler=_ok_handler(calls))
    assert await asyncio.wait_for(worker.run(max_jobs=1), timeout=20) == 1
    assert calls == []
    assert (await _job(db, org, job.job_id)).status == JobStatus.CANCELLED
    assert await _return_status(db, org, return_id) == "capturing"


@pytest.mark.db
async def test_t_q_18_submit_uses_the_spec_key_and_priority(db: Database) -> None:
    org = await _new_org(db)
    svc = IntakeService(db)
    ret = await svc.create_return(org_id=org, actor_id="op", order_id="ORD-9", unit_id="UNIT-0009")
    for shade in (30, 160):
        await svc.upload_photo(org_id=org, actor_id="op", return_id=ret.return_id, photo_bytes=_jpeg(shade))
    await svc.record_observation(org_id=org, actor_id="op", return_id=ret.return_id, observed_state="damaged")
    first = await svc.submit_return(org_id=org, actor_id="op", return_id=ret.return_id)
    again = await svc.submit_return(org_id=org, actor_id="op", return_id=ret.return_id)
    assert first.job_id == again.job_id, "re-submitting is idempotent"
    job = await _job(db, org, first.job_id)
    async with db.transaction(org) as conn:
        cur = await conn.execute(
            "SELECT sha256_analysis FROM rm.return_photos WHERE return_id = %s", (ret.return_id,)
        )
        hashes = [r["sha256_analysis"] for r in await cur.fetchall()]
    assert job.idempotency_key == compute_inspection_idempotency_key(org, ret.return_id, hashes)
    assert job.priority == 30, "operator tapped 'damaged' (+30, §10.3)"


@pytest.mark.db
async def test_t_q_19_admin_requeue_and_cancel(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    return_id, job = await _queued_return(db, org)
    worker = Worker(db, _settings(), concurrency=1)  # no handler → needs_attention
    await asyncio.wait_for(worker.run(max_jobs=1), timeout=20)
    assert await _return_status(db, org, return_id) == "needs_attention"
    requeued = await jobs_svc.retry_job(db, org, job.job_id)
    assert requeued.status == JobStatus.PENDING
    assert requeued.attempts == 0
    assert await _return_status(db, org, return_id) == "queued"
    cancelled = await jobs_svc.cancel_job(db, org, job.job_id)
    assert cancelled.status == JobStatus.CANCELLED
    listed = await jobs_svc.list_jobs(db, org)
    assert [j.job_id for j in listed] == [job.job_id]


@pytest.mark.db
async def test_t_q_20_heartbeat_row_and_lease_renewal(db: Database, quiet_queue: set[str]) -> None:
    """A running worker records its heartbeat; only the lease owner can renew a lease."""
    worker = Worker(db, _settings(), concurrency=1, worker_id=f"wrk_test_{new_id()[:8]}")
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.5)
    await worker.stop()
    await task
    async with db.transaction(None) as conn:
        cur = await conn.execute(
            "SELECT concurrency, now() - last_seen_at AS age FROM rm.worker_heartbeats WHERE worker_id = %s",
            (worker.worker_id,),
        )
        hb = await cur.fetchone()
    assert hb is not None
    assert hb["concurrency"] == 1
    assert hb["age"] < timedelta(seconds=30)

    org = await _new_org(db)
    _, job = await _queued_return(db, org)
    async with db.transaction(None) as conn:
        claimed = await JobQueue.claim_next_job(conn, "owner", lease_s=5, max_inflight_per_org=4)
    assert claimed is not None
    assert claimed.lease_expires_at is not None
    async with db.transaction(org) as conn:
        assert not await JobQueue.renew_lease(conn, org, job.job_id, "intruder", 600)
        assert await JobQueue.renew_lease(conn, org, job.job_id, "owner", 600)
    renewed = await _job(db, org, job.job_id)
    assert renewed.lease_expires_at is not None
    assert renewed.lease_expires_at > claimed.lease_expires_at + timedelta(seconds=500)


@pytest.mark.db
async def test_t_q_21_jobs_endpoint_scoped_to_org(db: Database) -> None:
    """GET /api/v1/jobs/{id}: 200 for the owner org, 404 (not 403) for another org, 403 without the scope."""
    import httpx

    from returns_manager.api.app import create_app
    from returns_manager.api.deps import Services
    from returns_manager.security import api_keys

    org_a, org_b = await _new_org(db), await _new_org(db)
    _, job = await _queued_return(db, org_a)
    key_a = await api_keys.create_key(
        db, org_id=org_a, name="a", scopes=["returns:read"], created_by="t", env="local"
    )
    key_b = await api_keys.create_key(
        db, org_id=org_b, name="b", scopes=["returns:read"], created_by="t", env="local"
    )
    key_a_metrics = await api_keys.create_key(
        db, org_id=org_a, name="m", scopes=["metrics:read"], created_by="t", env="local"
    )
    app = create_app()
    app.state.services = Services(settings=get_settings(), db=db, jwt=None, storage=None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        ok = await client.get(f"/api/v1/jobs/{job.job_id}", headers={"X-API-Key": key_a.plaintext})
        other = await client.get(f"/api/v1/jobs/{job.job_id}", headers={"X-API-Key": key_b.plaintext})
        noscope = await client.get(
            f"/api/v1/jobs/{job.job_id}", headers={"X-API-Key": key_a_metrics.plaintext}
        )
        anon = await client.get(f"/api/v1/jobs/{job.job_id}")
    assert ok.status_code == 200
    assert ok.json()["status"] == "pending"
    assert ok.json()["kind"] == "judgment"
    assert other.status_code == 404
    assert other.json()["detail"] is None, "a 404 must not reveal anything about another org's job"
    assert noscope.status_code == 403
    assert anon.status_code == 401


# ── db: fail-open (§10.6) ──────────────────────────────────────────────────


@pytest.mark.db
async def test_t_fo_01_timeout_leaves_return_pending_with_photos(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    return_id, job = await _queued_return(db, org)

    async def times_out(job: JobRecord) -> HandlerResult:
        raise TimeoutError("model request timed out after 180 s")

    worker = Worker(db, _settings(), concurrency=1, handler=times_out)
    await asyncio.wait_for(worker.run(max_jobs=1), timeout=20)
    failed = await _job(db, org, job.job_id)
    assert failed.status == JobStatus.FAILED_RETRYABLE
    assert failed.last_error_class == "timeout"
    assert failed.next_attempt_at > datetime.now(UTC)
    assert await _return_status(db, org, return_id) == "pending"
    assert await _photo_count(db, org, return_id) == 1


@pytest.mark.db
async def test_t_fo_02_retries_exhausted_needs_attention(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    return_id, job = await _queued_return(db, org)
    async with db.transaction(org) as conn:
        await conn.execute("UPDATE rm.inspection_jobs SET max_attempts = 1 WHERE job_id = %s", (job.job_id,))

    async def overloaded(job: JobRecord) -> HandlerResult:
        raise RuntimeError("503 model overloaded")

    worker = Worker(db, _settings(), concurrency=1, handler=overloaded)
    await asyncio.wait_for(worker.run(max_jobs=1), timeout=20)
    assert (await _job(db, org, job.job_id)).status == JobStatus.NEEDS_ATTENTION
    assert await _return_status(db, org, return_id) == "needs_attention"
    assert await _photo_count(db, org, return_id) == 1


@pytest.mark.db
async def test_t_fo_03_no_handler_never_produces_a_decision(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    return_id, job = await _queued_return(db, org)
    worker = Worker(db, _settings(), concurrency=1)
    await asyncio.wait_for(worker.run(max_jobs=1), timeout=20)
    failed = await _job(db, org, job.job_id)
    assert failed.status == JobStatus.NEEDS_ATTENTION
    assert failed.last_error_class == "configuration"
    assert await _return_status(db, org, return_id) == "needs_attention"


@pytest.mark.db
async def test_t_fo_04_handler_failure_rolls_back_its_writes(db: Database, quiet_queue: set[str]) -> None:
    org = await _new_org(db)
    return_id, _ = await _queued_return(db, org)

    async def writes_then_fails(job: JobRecord) -> HandlerResult:
        async def persist(conn: Any) -> None:
            await conn.execute(
                "INSERT INTO rm.operator_observations (obs_id, org_id, return_id, observed_state, "
                "operator_id) "
                "VALUES (%s, %s, %s, 'damaged', 'handler')",
                (new_id(), job.org_id, job.return_id),
            )
            raise RuntimeError("output failed schema validation")

        return HandlerResult(target_return_status=ReturnStatus.AWAITING_OPERATOR, persist=persist)

    worker = Worker(db, _settings(), concurrency=1, handler=writes_then_fails)
    await asyncio.wait_for(worker.run(max_jobs=1), timeout=20)
    async with db.transaction(org) as conn:
        cur = await conn.execute(
            "SELECT count(*) AS n FROM rm.operator_observations WHERE return_id = %s", (return_id,)
        )
        row = await cur.fetchone()
    assert row is not None
    assert row["n"] == 0, "a failed handler leaves no partial writes"
    assert await _return_status(db, org, return_id) == "pending"
