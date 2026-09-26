"""End-to-end judgment handler tests through the real worker, database and quota ledger.

They use a scripted model client (no quota spent) for happy path, X13 missing-reference,
provider-failure, daily-quota-429, dry-run, and what-if simulation cases (§3.3, §10.6,
§11.2a, §12.6; P5/P6 acceptance).
"""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from returns_manager.canonical.hashing import sha256_hex
from returns_manager.config import get_settings
from returns_manager.db.pool import Database
from returns_manager.disposition.simulate import simulate_for_return
from returns_manager.inspection.dryrun import dry_run
from returns_manager.inspection.service import JudgmentHandler
from returns_manager.intake.service import IntakeService
from returns_manager.jobs.worker import Worker
from returns_manager.llm import context as context_mod
from returns_manager.llm.client import ModelRequest, ModelResponse, ProviderError, response_from_raw
from returns_manager.llm.quota import QuotaGuard
from returns_manager.reference.models import ReferenceImage
from tests.unit import judgment_builders as b

pytestmark = pytest.mark.db


@dataclass
class MemStorage:
    photos_bucket: str = "rm-return-photos"
    objects: dict[str, bytes] = field(default_factory=dict)

    async def put(self, bucket: str, key: str, data: bytes, mime: str) -> None:
        self.objects[key] = data

    async def get(self, bucket: str, key: str) -> bytes:
        return self.objects[key]


@dataclass
class ScriptedClient:
    script: list[Any]
    requests: list[ModelRequest] = field(default_factory=list)

    async def create(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return response_from_raw(item, 1200)


def _jpeg(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    blocks = rng.integers(60, 190, size=(18, 24, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(np.kron(blocks, np.ones((50, 50, 1), dtype=np.uint8)), "RGB").save(
        buf, "JPEG", quality=90
    )
    return buf.getvalue()


def _output(**changes: Any) -> dict[str, Any]:
    ctx = b.context(b.card("org_demo_alpha", "SKU-LAMP-LED"), photos=("P1", "P2"))
    j = b.judgment(ctx, **changes)
    return {
        "id": f"int-{uuid.uuid4().hex[:6]}",
        "status": "completed",
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": j.model_dump_json()}]}],
        "usage": {
            "total_input_tokens": 6100,
            "total_output_tokens": 900,
            "total_thought_tokens": 400,
            "total_cached_tokens": 0,
        },
    }


@dataclass
class Setup:
    org: str
    return_id: str
    job_id: str
    storage: MemStorage
    settings: Any


async def _setup(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_card: bool = True,
    sku: str = "SKU-LAMP-LED",
) -> Setup:
    org = f"org_t{uuid.uuid4().hex[:12]}"
    products_dir = tmp_path / "products"
    image = _jpeg(7)
    img_path = products_dir / org / "images" / sku / "front.jpg"
    img_path.parent.mkdir(parents=True)
    img_path.write_bytes(image)
    monkeypatch.setattr(context_mod, "PRODUCTS_DIR", products_dir)  # rubrics/categories stay real
    card = b.card("org_demo_alpha", "SKU-LAMP-LED").model_copy(update={"org_id": org})
    card = card.model_copy(
        update={
            "reference_images": [
                ReferenceImage(
                    id="ref_front", view="front", path=f"images/{sku}/front.jpg", sha256=sha256_hex(image)
                )
            ]
        }
    )
    async with db.transaction(org) as conn:
        await conn.execute(
            "INSERT INTO rm.organizations (org_id, name) VALUES (%s, 'inspection test')", (org,)
        )
        await conn.execute(
            "INSERT INTO rm.orders (org_id, order_id, unit_id, ordered_sku, quantity, "
            "fulfilment_route, ordered_at) "
            "VALUES (%s, 'ORD-T-1', 'UNIT-0014', %s, 1, 'fba', now())",
            (org, sku),
        )
        if with_card:
            await conn.execute(
                "INSERT INTO rm.products (org_id, sku, card_version, title, brand, category_key, "
                "card_sha256, card) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    org,
                    sku,
                    card.version,
                    card.title,
                    card.brand,
                    card.category_key,
                    "0" * 64,
                    json.dumps(card.model_dump(by_alias=True, mode="json")),
                ),
            )
    storage = MemStorage()
    intake = IntakeService(db, storage)  # type: ignore[arg-type]
    ret = await intake.create_return(org_id=org, actor_id="op", order_id="ORD-T-1", unit_id="UNIT-0014")
    for seed in (1, 2):
        await intake.upload_photo(org_id=org, actor_id="op", return_id=ret.return_id, photo_bytes=_jpeg(seed))
    sub = await intake.submit_return(org_id=org, actor_id="op", return_id=ret.return_id)
    settings = get_settings().model_copy(
        update={
            "rm_judgment_model": f"test-model-{uuid.uuid4().hex[:8]}",
            "rm_daily_request_budget_judgment": 10,
        }
    )
    return Setup(org, ret.return_id, sub.job_id, storage, settings)


async def _run(db: Database, s: Setup, client: ScriptedClient) -> None:
    handler = JudgmentHandler(db, s.settings, client, s.storage, QuotaGuard(db, s.settings))  # type: ignore[arg-type]
    worker = Worker(db, s.settings, concurrency=1, handler=handler)
    await asyncio.wait_for(worker.run(max_jobs=1), timeout=30)


async def _one(db: Database, org: str, sql: str, *args: Any) -> Any:
    async with db.transaction(org) as conn:
        cur = await conn.execute(sql, args)
        return await cur.fetchone()


async def test_happy_path_one_request_persisted_atomically(
    db: Database, quiet_queue: set[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await _setup(db, tmp_path, monkeypatch)
    client = ScriptedClient([_output()])
    await _run(db, s, client)
    assert len(client.requests) == 1
    ret = await _one(db, s.org, "SELECT status FROM rm.returns WHERE return_id = %s", s.return_id)
    run = await _one(db, s.org, "SELECT * FROM rm.inspection_runs WHERE return_id = %s", s.return_id)
    res = await _one(db, s.org, "SELECT * FROM rm.inspection_results WHERE return_id = %s", s.return_id)
    job = await _one(db, s.org, "SELECT status FROM rm.inspection_jobs WHERE job_id = %s", s.job_id)
    assert job["status"] == "succeeded"
    assert run["status"] == "completed"
    assert run["api_requests"] == 1
    assert run["usage"]["total_input_tokens"] == 6100
    assert run["output_sha256"] is not None
    assert "thought" not in json.dumps(run["output"]).lower()
    assert run["context_manifest"]["rubric"]["verification_status"] == "unverified_substitute"
    # opened lamp, like new, complete, identity proven on the body → electronics functional test → refurbish
    assert res["identity_match"] == "yes"
    assert res["recommended_disposition"] == "refurbish"
    assert res["amazon_condition"] == "Used - Like New"
    assert ret["status"] == "awaiting_operator"
    keys = [c["check_key"] for c in res["checks"]]
    assert keys[:4] == ["photo_quality", "unit_presence", "identity", "completeness"]
    model_check = next(c for c in res["checks"] if c["check_key"] == "identity")
    assert model_check["model_version"].startswith(s.settings.rm_judgment_model + "@judgment-")
    assert model_check["latency_ms"] == 1200
    ledger = await _one(
        db,
        None,
        "SELECT requests_used FROM rm.model_request_ledger WHERE model_id = %s",
        s.settings.rm_judgment_model,
    )  # type: ignore[arg-type]
    assert ledger["requests_used"] == 1  # reserved 2, used 1, released 1

    sim = None
    async with db.transaction(s.org) as conn:
        sim = await simulate_for_return(
            conn, s.return_id, {"cosmetic_grade": "used_good", "listing_blockers": []}
        )
    assert sim["mode"] == "SIMULATION"
    assert sim["before"]["recommended_disposition"] == "refurbish"
    assert sim["after"]["recommended_disposition"] == "liquidate"
    n = await _one(
        db, s.org, "SELECT count(*) AS n FROM rm.inspection_results WHERE return_id = %s", s.return_id
    )
    assert n["n"] == 1, "simulation writes nothing"


async def test_x13_missing_card_no_model_call(
    db: Database, quiet_queue: set[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await _setup(db, tmp_path, monkeypatch, with_card=False)
    client = ScriptedClient([])
    await _run(db, s, client)
    assert client.requests == [], "no request may be sent without product reference data"
    ret = await _one(db, s.org, "SELECT status FROM rm.returns WHERE return_id = %s", s.return_id)
    run = await _one(
        db,
        s.org,
        "SELECT status, skip_reasons, api_requests FROM rm.inspection_runs WHERE return_id = %s",
        s.return_id,
    )
    res = await _one(db, s.org, "SELECT * FROM rm.inspection_results WHERE return_id = %s", s.return_id)
    photos = await _one(
        db, s.org, "SELECT count(*) AS n FROM rm.return_photos WHERE return_id = %s", s.return_id
    )
    assert ret["status"] == "awaiting_review"
    assert run["status"] == "skipped"
    assert run["skip_reasons"] == ["no_product_reference"]
    assert run["api_requests"] == 0
    assert res["recommended_disposition"] is None
    assert res["no_recommendation_reason"] == "no_product_reference"
    assert all(c["verdict"] == "UNCERTAIN" for c in res["checks"] if c["check_key"] != "photo_quality")
    assert photos["n"] == 2


async def test_provider_failure_fails_open_and_keeps_the_run(
    db: Database, quiet_queue: set[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await _setup(db, tmp_path, monkeypatch)
    await _run(db, s, ScriptedClient([ProviderError("server_error", "503 overloaded", status_code=503)]))
    ret = await _one(db, s.org, "SELECT status FROM rm.returns WHERE return_id = %s", s.return_id)
    job = await _one(
        db, s.org, "SELECT status, last_error_class FROM rm.inspection_jobs WHERE job_id = %s", s.job_id
    )
    run = await _one(
        db,
        s.org,
        "SELECT status, error_class, api_requests FROM rm.inspection_runs WHERE return_id = %s",
        s.return_id,
    )
    res = await _one(
        db, s.org, "SELECT count(*) AS n FROM rm.inspection_results WHERE return_id = %s", s.return_id
    )
    assert ret["status"] == "pending"
    assert (job["status"], job["last_error_class"]) == ("failed_retryable", "server_error")
    assert (run["status"], run["error_class"], run["api_requests"]) == ("failed", "server_error", 1)
    assert res["n"] == 0, "a failure never produces a decision"


async def test_daily_quota_429_holds_until_reset(
    db: Database, quiet_queue: set[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await _setup(db, tmp_path, monkeypatch)
    worker_task_client = ScriptedClient([ProviderError("quota_exhausted", "daily quota", status_code=429)])
    handler = JudgmentHandler(
        db,
        s.settings,
        worker_task_client,
        s.storage,
        QuotaGuard(db, s.settings),  # type: ignore[arg-type]
    )
    worker = Worker(db, s.settings, concurrency=1, handler=handler)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(1.5)  # A held job is intentionally not counted as finished.
    await worker.stop()
    await asyncio.wait_for(task, timeout=10)
    job = await _one(
        db,
        s.org,
        "SELECT status, attempts, last_error_class, next_attempt_at > now() + interval '1 minute' "
        "AS later FROM rm.inspection_jobs WHERE job_id = %s",
        s.job_id,
    )
    ret = await _one(db, s.org, "SELECT status FROM rm.returns WHERE return_id = %s", s.return_id)
    assert job["status"] == "failed_retryable"
    assert job["last_error_class"] == "quota_exhausted"
    assert job["attempts"] == 0
    assert job["later"]
    assert ret["status"] == "pending"
    status = await QuotaGuard(db, s.settings).status(s.settings.rm_judgment_model, "judgment")
    assert status.requests_remaining == 0, "a provider daily 429 marks the model exhausted for the day"


async def test_dry_run_reports_estimate_and_quota_without_calling_the_model(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await _setup(db, tmp_path, monkeypatch)
    d = await dry_run(db, s.settings, s.storage, s.org, s.return_id)  # type: ignore[arg-type]
    assert d.would_call_model
    assert d.summary["estimated_input_tokens"] > 1120 * 2
    assert d.summary["quota"]["remaining_today"] == 10
    assert d.summary["quota_covers_session"]
    assert d.summary["cost_label"] == "paid-equivalent (free tier used)"
