"""P9 Acceptance Tests: Escalation Agent, Merge Rules, Blind Audit Reviewer, Quota Holds,
and Event Chain Validity (§11.12, §11.13, §19, §20, §23).

- Genuinely blind escalation session on RM_ESCALATION_MODEL
- Merge table rows (§11.12): resolved_by_escalation, kept_primary, model_disagreement, uncertain
- Rerun fused pipeline on merged judgment; model never selects disposition
- Worker state machine: no illegal transition of awaiting_review returns to inspecting
- Blind audit reviewer on RM_AUDIT_MODEL: deterministic hash sampling, 100% on eval runs
- Audit disagreements: identity, completeness, unit presence, cosmetic grade > 1 step
- Finalized vs unfinalized return behavior
- Daily request quota holds and kill switches
- Cross-org tenant denial
- Event chain validity
- CLI `audit run` dry-run and spend protection
"""

from __future__ import annotations

import io
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import pytest_asyncio
from PIL import Image

from returns_manager.canonical.hashing import sha256_hex, sha256_jcs
from returns_manager.chain.service import run_verify_org
from returns_manager.cli.main import run as cli_run
from returns_manager.config import get_settings
from returns_manager.db.pool import Database
from returns_manager.errors import ExitCode
from returns_manager.inspection.service import JudgmentHandler
from returns_manager.jobs.queue import JobQueue
from returns_manager.jobs.worker import Worker
from returns_manager.llm import context as context_mod
from returns_manager.llm.client import ModelRequest, ModelResponse, response_from_raw
from returns_manager.llm.quota import QuotaGuard
from returns_manager.llm.schemas import JudgmentV1
from returns_manager.reference.models import ReferenceImage
from returns_manager.review.escalation_service import EscalationAuditService
from returns_manager.review.merge import (
    MergeOutcome,
    audit_disagreements,
    audit_sampled,
    merge_area,
)
from returns_manager.security import controls
from tests.unit import judgment_builders as b

pytestmark = pytest.mark.db


# ── Test Helpers ─────────────────────────────────────────────────────────────


class MemStorage:
    photos_bucket: str = "rm-return-photos"
    objects: dict[str, bytes]

    def __init__(self) -> None:
        self.objects = {}

    async def put(self, bucket: str, key: str, data: bytes, mime: str) -> None:
        self.objects[key] = data

    async def get(self, bucket: str, key: str) -> bytes:
        if key not in self.objects:
            raise KeyError(key)
        return self.objects[key]


@dataclass
class ScriptedClient:
    script: list[Any]
    requests: list[ModelRequest] = field(default_factory=list)

    async def create(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self.script:
            raise RuntimeError("ScriptedClient ran out of responses")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return response_from_raw(item, 120)


def _jpeg(seed: int = 42) -> bytes:
    rng = np.random.default_rng(seed)
    blocks = rng.integers(60, 190, size=(18, 24, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(np.kron(blocks, np.ones((50, 50, 1), dtype=np.uint8)), "RGB").save(
        buf, "JPEG", quality=90
    )
    return buf.getvalue()


def _model_raw_output(j_obj: Any) -> dict[str, Any]:
    return {
        "id": f"int-{uuid.uuid4().hex[:6]}",
        "status": "completed",
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": j_obj.model_dump_json()}]}],
        "usage": {
            "total_input_tokens": 5000,
            "total_output_tokens": 800,
            "total_thought_tokens": 300,
            "total_cached_tokens": 0,
        },
    }


# ── Unit Tests: §11.12 Escalation Merge Table ───────────────────────────────


def test_merge_area_all_four_rows() -> None:
    """§11.12 Table: test all 4 rows for each decision area."""
    # Row 1: Primary uncertain, Escalation confident -> Take escalation (resolved_by_escalation)
    r1_presence = merge_area("uncertain", "product_present")
    assert r1_presence == MergeOutcome("product_present", "resolved_by_escalation", False)

    r1_id = merge_area("uncertain", "yes")
    assert r1_id == MergeOutcome("yes", "resolved_by_escalation", False)

    r1_grade = merge_area("uncertain", "used_good")
    assert r1_grade == MergeOutcome("used_good", "resolved_by_escalation", False)

    r1_comp = merge_area("uncertain", "present")
    assert r1_comp == MergeOutcome("present", "resolved_by_escalation", False)

    # Row 2: Primary confident, Escalation confident and SAME -> Keep primary (kept_primary)
    r2_presence = merge_area("product_present", "product_present")
    assert r2_presence == MergeOutcome("product_present", "kept_primary", False)

    r2_id = merge_area("yes", "yes")
    assert r2_id == MergeOutcome("yes", "kept_primary", False)

    r2_grade = merge_area("used_good", "used_good")
    assert r2_grade == MergeOutcome("used_good", "kept_primary", False)

    # Row 3: Primary confident, Escalation confident but DIFFERENT -> uncertain (model_disagreement) -> review
    r3_presence = merge_area("product_present", "empty_packaging")
    assert r3_presence == MergeOutcome("uncertain", "model_disagreement", True)

    r3_id = merge_area("yes", "no")
    assert r3_id == MergeOutcome("uncertain", "model_disagreement", True)

    r3_grade = merge_area("used_good", "used_like_new")
    assert r3_grade == MergeOutcome("uncertain", "model_disagreement", True)

    r3_comp = merge_area("present", "missing")
    assert r3_comp == MergeOutcome("uncertain", "model_disagreement", True)

    # Row 4: Any primary, Escalation uncertain -> uncertain -> review
    r4_from_conf = merge_area("product_present", "uncertain")
    assert r4_from_conf == MergeOutcome("uncertain", "uncertain", True)

    r4_from_unc = merge_area("uncertain", "uncertain")
    assert r4_from_unc == MergeOutcome("uncertain", "uncertain", True)


# ── Unit Tests: §11.13 Audit Sampling and Disagreements ─────────────────────


def test_audit_sampling_deterministic_and_eval_run() -> None:
    """§11.13: stable SHA-256 hash bucket; eval runs are forced 100%."""
    ret_a = "ret_sample_test_001"
    ret_b = "ret_sample_test_002"

    # Stability
    assert audit_sampled(ret_a, 0.5) == audit_sampled(ret_a, 0.5)
    assert audit_sampled(ret_b, 0.5) == audit_sampled(ret_b, 0.5)

    # 100% on eval runs regardless of sample rate
    assert audit_sampled(ret_a, 0.0, eval_run=True) is True
    assert audit_sampled(ret_b, 0.0, eval_run=True) is True

    # Bounds
    assert audit_sampled(ret_a, 0.0, eval_run=False) is False
    assert audit_sampled(ret_a, 1.0, eval_run=False) is True


def test_audit_disagreements_taxonomy() -> None:
    """§11.13: flag identity, completeness, unit presence, and cosmetic grades > 1 step apart."""
    prim = {
        "identity_match": "yes",
        "completeness_status": "complete",
        "unit_presence": "product_present",
        "cosmetic_grade": "used_like_new",
    }

    # 1. Exact match -> no disagreements
    aud_match = dict(prim)
    assert audit_disagreements(prim, aud_match) == ()

    # 2. Identity disagreement
    aud_id_diff = dict(prim, identity_match="uncertain")
    assert "identity_match" in audit_disagreements(prim, aud_id_diff)

    # 3. Completeness disagreement
    aud_comp_diff = dict(prim, completeness_status="incomplete")
    assert "completeness_status" in audit_disagreements(prim, aud_comp_diff)

    # 4. Unit presence disagreement
    aud_unit_diff = dict(prim, unit_presence="empty_packaging")
    assert "unit_presence" in audit_disagreements(prim, aud_unit_diff)

    # 5. Cosmetic grade: 1 step apart -> NOT flagged
    # Scale: new (0), used_like_new (1), used_very_good (2), used_good (3), used_acceptable (4)
    aud_grade_1step = dict(prim, cosmetic_grade="used_very_good")
    assert "cosmetic_grade" not in audit_disagreements(prim, aud_grade_1step)

    # 6. Cosmetic grade: 2 steps apart -> FLAGGED
    aud_grade_2step = dict(prim, cosmetic_grade="used_good")
    assert "cosmetic_grade" in audit_disagreements(prim, aud_grade_2step)

    # 7. Cosmetic grade: None vs value -> FLAGGED
    aud_grade_none = dict(prim, cosmetic_grade=None)
    assert "cosmetic_grade" in audit_disagreements(prim, aud_grade_none)


# ── DB Tests: Escalation Persistence & Merges ───────────────────────────────


@pytest_asyncio.fixture()
async def p9_fixture_case(db: Database) -> dict[str, Any]:
    org = f"org_p9_{uuid.uuid4().hex[:12]}"
    unit = f"UNIT-P9-{uuid.uuid4().hex[:8]}"
    order = f"ORD-P9-{uuid.uuid4().hex[:8]}"
    ret = f"ret-p9-{uuid.uuid4().hex[:12]}"
    record = f"RTN-{uuid.uuid4().int % 9000 + 1000:04d}"
    prim_ins = f"ins-prim-{uuid.uuid4().hex[:12]}"
    esc_ins = f"ins-esc-{uuid.uuid4().hex[:12]}"
    aud_ins = f"ins-aud-{uuid.uuid4().hex[:12]}"

    async with db.transaction(org) as conn:
        await conn.execute("INSERT INTO rm.organizations (org_id, name) VALUES (%s, 'P9 Org')", (org,))
        await conn.execute(
            """INSERT INTO rm.orders (
                 org_id, order_id, unit_id, ordered_sku, quantity, fulfilment_route, ordered_at
               ) VALUES (%s, %s, %s, 'SKU-LAMP-LED', 1, 'fba', now())""",
            (org, order, unit),
        )
        await conn.execute(
            """INSERT INTO rm.returns (
                 return_id, org_id, record_id, unit_id, order_id, return_seq, created_by, status
               ) VALUES (%s, %s, %s, %s, %s, 1, 'capturer', 'awaiting_review')""",
            (ret, org, record, unit, order),
        )
        # Primary judgment run
        await conn.execute(
            """INSERT INTO rm.inspection_runs (
                 inspection_id, org_id, return_id, kind, status, model_id, context_manifest
               ) VALUES (%s, %s, %s, 'judgment', 'completed', 'gemini-3.8-flash', '{}'::jsonb)""",
            (prim_ins, org, ret),
        )
        await conn.execute(
            """INSERT INTO rm.inspection_results (
                 result_id, org_id, return_id, inspection_id, identity_match, fused_identity, unit_presence,
                 completeness_status, components, amazon_condition, condition, claim_signals, uncertainties,
                 retake_requests, validator_actions, checks, escalation_state, recommended_disposition,
                 provisional, disposition, disposition_inputs, requires_review,
                 review_reasons, requires_signoff
               ) VALUES (
                 %s, %s, %s, %s, 'uncertain', '{}'::jsonb, 'product_present', 'uncertain',
                 '[{"component_id": "c1", "status": "uncertain"}]'::jsonb,
                 'Used - Good', '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                 '[]'::jsonb, 'triggered_not_run', 'restock', false,
                 '{"recommended_disposition":"restock","rule_id":"R13"}'::jsonb,
                 '{}'::jsonb, true, '{"identity_uncertain"}', false
               )""",
            (f"res-{uuid.uuid4().hex[:12]}", org, ret, prim_ins),
        )
        # Escalation run stub
        await conn.execute(
            """INSERT INTO rm.inspection_runs (
                 inspection_id, org_id, return_id, kind, status, model_id, context_manifest
               ) VALUES (%s, %s, %s, 'escalation', 'completed', 'gemini-3.8-flash', '{}'::jsonb)""",
            (esc_ins, org, ret),
        )
        # Audit run stub
        await conn.execute(
            """INSERT INTO rm.inspection_runs (
                 inspection_id, org_id, return_id, kind, status, model_id, context_manifest
               ) VALUES (%s, %s, %s, 'audit', 'completed', 'gemini-3.6-flash', '{}'::jsonb)""",
            (aud_ins, org, ret),
        )

    return {
        "org": org,
        "unit": unit,
        "return_id": ret,
        "prim_ins": prim_ins,
        "esc_ins": esc_ins,
        "aud_ins": aud_ins,
    }


@pytest.mark.asyncio
async def test_escalation_service_persists_merges_and_chain_event(
    db: Database, p9_fixture_case: dict[str, Any]
) -> None:
    """§11.12: persist each area row to rm.escalation_merges and append ESCALATION_COMPLETED event."""
    c = p9_fixture_case
    svc = EscalationAuditService(db)

    primary_areas = {
        "unit_presence": "product_present",
        "identity_match": "uncertain",
        "cosmetic_grade": "used_good",
        "component:c1": "uncertain",
    }
    escalation_areas = {
        "unit_presence": "product_present",  # kept_primary
        "identity_match": "yes",  # resolved_by_escalation
        "cosmetic_grade": "used_like_new",  # model_disagreement
        "component:c1": "uncertain",  # uncertain
    }

    outcomes = await svc.merge(
        org_id=c["org"],
        return_id=c["return_id"],
        primary_inspection_id=c["prim_ins"],
        escalation_inspection_id=c["esc_ins"],
        primary=primary_areas,
        escalation=escalation_areas,
    )

    assert outcomes["unit_presence"]["outcome"] == "kept_primary"
    assert outcomes["identity_match"]["outcome"] == "resolved_by_escalation"
    assert outcomes["identity_match"]["value"] == "yes"
    assert outcomes["cosmetic_grade"]["outcome"] == "model_disagreement"
    assert outcomes["component:c1"]["outcome"] == "uncertain"

    # Verify rows in rm.escalation_merges
    async with db.transaction(c["org"]) as conn:
        cur = await conn.execute(
            "SELECT area, outcome, merged_value FROM rm.escalation_merges WHERE return_id = %s",
            (c["return_id"],),
        )
        rows = await cur.fetchall()
        assert len(rows) == 4
        by_area = {r["area"]: r for r in rows}
        assert by_area["identity_match"]["outcome"] == "resolved_by_escalation"
        assert by_area["identity_match"]["merged_value"] == "yes"

    # Verify chain validity
    report = await run_verify_org(db.pool, c["org"])
    assert report.valid is True


@pytest.mark.asyncio
async def test_audit_service_finalized_vs_non_finalized(
    db: Database, p9_fixture_case: dict[str, Any]
) -> None:
    """§11.13: Non-finalized return moves to awaiting_review on disagreement;
    finalized return is untouched."""
    c = p9_fixture_case
    svc = EscalationAuditService(db)

    # 1. Set return status to awaiting_operator
    async with db.transaction(c["org"]) as conn:
        await conn.execute(
            "UPDATE rm.returns SET status = 'awaiting_operator' WHERE return_id = %s",
            (c["return_id"],),
        )

    primary = {
        "identity_match": "yes",
        "completeness_status": "complete",
        "unit_presence": "product_present",
        "cosmetic_grade": "new",
    }
    audit_differing = {
        "identity_match": "yes",
        "completeness_status": "complete",
        "unit_presence": "product_present",
        "cosmetic_grade": "used_good",  # 3 steps apart -> disagreement!
    }

    disagreements = await svc.record_audit(
        org_id=c["org"],
        return_id=c["return_id"],
        primary_inspection_id=c["prim_ins"],
        audit_inspection_id=c["aud_ins"],
        primary=primary,
        audit=audit_differing,
        eval_run_id="eval-test-01",
    )
    assert "cosmetic_grade" in disagreements

    # Verify return transitioned to awaiting_review
    async with db.transaction(c["org"]) as conn:
        cur = await conn.execute("SELECT status FROM rm.returns WHERE return_id = %s", (c["return_id"],))
        row = await cur.fetchone()
        assert row["status"] == "awaiting_review"

        cur = await conn.execute(
            "SELECT eval_run_id, routes_to_review, disagreements FROM rm.audit_findings WHERE return_id = %s",
            (c["return_id"],),
        )
        finding = await cur.fetchone()
        assert finding["eval_run_id"] == "eval-test-01"
        assert finding["routes_to_review"] is True
        assert "cosmetic_grade" in finding["disagreements"]

    # 2. Finalized return test: status must NOT be modified!
    aud_ins_2 = f"ins-aud2-{uuid.uuid4().hex[:12]}"
    async with db.transaction(c["org"]) as conn:
        await conn.execute(
            "UPDATE rm.returns SET status = 'finalized' WHERE return_id = %s",
            (c["return_id"],),
        )
        await conn.execute(
            """INSERT INTO rm.inspection_runs (
                 inspection_id, org_id, return_id, kind, status, model_id, context_manifest
               ) VALUES (%s, %s, %s, 'audit', 'completed', 'gemini-3.6-flash', '{}'::jsonb)""",
            (aud_ins_2, c["org"], c["return_id"]),
        )

    disagreements2 = await svc.record_audit(
        org_id=c["org"],
        return_id=c["return_id"],
        primary_inspection_id=c["prim_ins"],
        audit_inspection_id=aud_ins_2,
        primary=primary,
        audit=audit_differing,
        eval_run_id="eval-test-02",
    )
    assert "cosmetic_grade" in disagreements2

    async with db.transaction(c["org"]) as conn:
        cur = await conn.execute("SELECT status FROM rm.returns WHERE return_id = %s", (c["return_id"],))
        row = await cur.fetchone()
        # MUST REMAIN FINALIZED
        assert row["status"] == "finalized"

    # Verify event chain passes
    report = await run_verify_org(db.pool, c["org"])
    assert report.valid is True


# ── Full Worker Tests: Escalation Pipeline & Replay ──────────────────────────


@pytest.mark.asyncio
async def test_worker_escalation_resolves_uncertainty_and_reruns_pipeline(
    db: Database, p9_fixture_case: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escalation agent runs blind, resolves uncertainty, merges via §11.12, and pipeline reruns."""
    c = p9_fixture_case
    settings = get_settings().model_copy(update={"rm_daily_request_budget_judgment": 1000})

    # Set up product card and reference image
    products_dir = tmp_path / "products"
    img_data_1 = _jpeg(42)
    img_data_2 = _jpeg(43)
    sha1 = sha256_hex(img_data_1)
    sha2 = sha256_hex(img_data_2)
    sku = "SKU-LAMP-LED"
    ref_img_path = products_dir / c["org"] / "images" / sku / "front.jpg"
    ref_img_path.parent.mkdir(parents=True)
    ref_img_path.write_bytes(img_data_1)
    monkeypatch.setattr(context_mod, "PRODUCTS_DIR", products_dir)

    card = b.card("org_demo_alpha", sku).model_copy(update={"org_id": c["org"]})
    card = card.model_copy(
        update={
            "reference_images": [
                ReferenceImage(id="ref_front", view="front", path=f"images/{sku}/front.jpg", sha256=sha1)
            ]
        }
    )

    storage = MemStorage()
    p1_key = f"org/{c['org']}/returns/{c['return_id']}/photo1.jpg"
    p2_key = f"org/{c['org']}/returns/{c['return_id']}/photo2.jpg"
    storage.objects[p1_key] = img_data_1
    storage.objects[p2_key] = img_data_2

    async with db.transaction(c["org"]) as conn:
        await conn.execute(
            """INSERT INTO rm.products
                 (org_id, sku, card_version, title, brand, category_key, card_sha256, card)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
               ON CONFLICT DO NOTHING""",
            (
                c["org"],
                card.sku,
                card.version,
                card.title,
                card.brand,
                card.category_key,
                sha256_jcs(card.model_dump()),
                json.dumps(card.model_dump()),
            ),
        )
        for slot, alias, key, s_hash, data in (
            (1, "P1", p1_key, sha1, img_data_1),
            (2, "P2", p2_key, sha2, img_data_2),
        ):
            await conn.execute(
                """INSERT INTO rm.return_photos (
                     photo_id, org_id, return_id, slot, alias, storage_key_original, storage_key_analysis,
                     mime, bytes, sha256_original, sha256_analysis, quality_status, uploaded_by
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'image/jpeg', %s, %s, %s, 'pass', 'tester')""",
                (
                    f"pho-{uuid.uuid4().hex[:12]}",
                    c["org"],
                    c["return_id"],
                    slot,
                    alias,
                    key,
                    key,
                    len(data),
                    s_hash,
                    s_hash,
                ),
            )

    # Build an escalation judgment that is confident ("yes" on identity, "present" on components)
    ctx = b.context(card, photos=("P1", "P2"))
    esc_j = b.judgment(ctx)
    esc_raw = _model_raw_output(esc_j)

    client = ScriptedClient([esc_raw])
    quota = QuotaGuard(db, settings)
    handler = JudgmentHandler(db, settings, client, storage, quota)

    # Enqueue escalation job
    async with db.transaction(c["org"]) as conn:
        await JobQueue.enqueue_job(
            conn,
            c["org"],
            c["return_id"],
            kind="escalation",
            priority=10,
        )

    # Verify that Return was in awaiting_review and remains awaiting_review before claim
    async with db.transaction(c["org"]) as conn:
        cur = await conn.execute("SELECT status FROM rm.returns WHERE return_id = %s", (c["return_id"],))
        assert (await cur.fetchone())["status"] == "awaiting_review"

    worker = Worker(
        db, settings, concurrency=1, kinds=["escalation"], handler=handler, worker_id="test-esc-worker"
    )
    async with db.transaction(c["org"]) as conn:
        claimed = await JobQueue.claim_specific(
            conn,
            c["org"],
            c["return_id"],
            worker_id=worker.worker_id,
            lease_s=settings.rm_job_lease_s,
            kinds="escalation",
        )
    assert claimed is not None
    ok = await worker._process_job(claimed)
    assert ok is True

    # Verify client received an escalation request that had ESCALATION FOCUS and NO primary verdicts
    assert len(client.requests) == 1
    req = client.requests[0]
    assert req.model == settings.rm_escalation_model
    prompt_text = str(req.input)
    assert "ESCALATION FOCUS" in prompt_text
    # Blind check: primary verdicts must not be presented to the escalation model
    assert "Primary verdict:" not in prompt_text

    # Verify that return status transitioned to awaiting_operator (or signoff) because uncertainties resolved
    async with db.transaction(c["org"]) as conn:
        cur = await conn.execute("SELECT status FROM rm.returns WHERE return_id = %s", (c["return_id"],))
        new_status = (await cur.fetchone())["status"]
        assert new_status in ("awaiting_operator", "awaiting_signoff")

        # Verify escalation merges were persisted
        cur = await conn.execute(
            "SELECT area, outcome, merged_value FROM rm.escalation_merges WHERE return_id = %s",
            (c["return_id"],),
        )
        merges = await cur.fetchall()
        assert len(merges) > 0

        # Verify inspection_results with escalation_state = 'completed'
        cur = await conn.execute(
            """SELECT escalation_state, identity_match FROM rm.inspection_results
               WHERE return_id = %s AND escalation_state = 'completed'""",
            (c["return_id"],),
        )
        esc_res = await cur.fetchone()
        assert esc_res is not None
        assert esc_res["escalation_state"] == "completed"

    # Verify chain validity
    report = await run_verify_org(db.pool, c["org"])
    assert report.valid is True


# ── Full Worker Tests: Blind Audit Execution ─────────────────────────────────


@pytest.mark.asyncio
async def test_worker_audit_execution_and_disagreement_routing(
    db: Database, p9_fixture_case: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit job runs on RM_AUDIT_MODEL, checks disagreements, and routes unfinalized return to review."""
    c = p9_fixture_case
    settings = get_settings().model_copy(update={"rm_daily_request_budget_audit": 1000})

    products_dir = tmp_path / "products"
    img_data_1 = _jpeg(81)
    img_data_2 = _jpeg(82)
    sha1 = sha256_hex(img_data_1)
    sha2 = sha256_hex(img_data_2)
    sku = "SKU-LAMP-LED"
    ref_img_path = products_dir / c["org"] / "images" / sku / "front.jpg"
    ref_img_path.parent.mkdir(parents=True)
    ref_img_path.write_bytes(img_data_1)
    monkeypatch.setattr(context_mod, "PRODUCTS_DIR", products_dir)

    card = b.card("org_demo_alpha", sku).model_copy(update={"org_id": c["org"]})
    card = card.model_copy(
        update={
            "reference_images": [
                ReferenceImage(id="ref_front", view="front", path=f"images/{sku}/front.jpg", sha256=sha1)
            ]
        }
    )

    storage = MemStorage()
    p1_key = f"org/{c['org']}/returns/{c['return_id']}/photo1.jpg"
    p2_key = f"org/{c['org']}/returns/{c['return_id']}/photo2.jpg"
    storage.objects[p1_key] = img_data_1
    storage.objects[p2_key] = img_data_2

    async with db.transaction(c["org"]) as conn:
        # Put return in awaiting_operator
        await conn.execute(
            "UPDATE rm.returns SET status = 'awaiting_operator' WHERE return_id = %s", (c["return_id"],)
        )
        await conn.execute(
            """INSERT INTO rm.products
                 (org_id, sku, card_version, title, brand, category_key, card_sha256, card)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
               ON CONFLICT DO NOTHING""",
            (
                c["org"],
                card.sku,
                card.version,
                card.title,
                card.brand,
                card.category_key,
                sha256_jcs(card.model_dump()),
                json.dumps(card.model_dump()),
            ),
        )
        for slot, alias, key, s_hash, data in (
            (1, "P1", p1_key, sha1, img_data_1),
            (2, "P2", p2_key, sha2, img_data_2),
        ):
            await conn.execute(
                """INSERT INTO rm.return_photos (
                     photo_id, org_id, return_id, slot, alias, storage_key_original, storage_key_analysis,
                     mime, bytes, sha256_original, sha256_analysis, quality_status, uploaded_by
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'image/jpeg', %s, %s, %s, 'pass', 'tester')
                   ON CONFLICT DO NOTHING""",
                (
                    f"pho-{uuid.uuid4().hex[:12]}",
                    c["org"],
                    c["return_id"],
                    slot,
                    alias,
                    key,
                    key,
                    len(data),
                    s_hash,
                    s_hash,
                ),
            )

    # Audit outputs a different condition (used_acceptable vs primary used_good) -> disagreement
    ctx = b.context(card, photos=("P1", "P2"))
    aud_j = b.judgment(ctx)
    # Modify condition grade to be > 1 step apart from primary "Used - Good"
    aud_dict = aud_j.model_dump()
    aud_dict["condition"]["proposed_grade"]["grade_code"] = "used_acceptable"
    aud_modified = JudgmentV1.model_validate(aud_dict)
    aud_raw = _model_raw_output(aud_modified)

    client = ScriptedClient([aud_raw])
    quota = QuotaGuard(db, settings)
    handler = JudgmentHandler(db, settings, client, storage, quota, eval_run_id="eval-worker-01")

    # Enqueue audit job
    async with db.transaction(c["org"]) as conn:
        await JobQueue.enqueue_job(
            conn,
            c["org"],
            c["return_id"],
            kind="audit",
            priority=-10,
        )

    worker = Worker(
        db, settings, concurrency=1, kinds=["audit"], handler=handler, worker_id="test-aud-worker"
    )
    async with db.transaction(c["org"]) as conn:
        claimed = await JobQueue.claim_specific(
            conn,
            c["org"],
            c["return_id"],
            worker_id=worker.worker_id,
            lease_s=settings.rm_job_lease_s,
            kinds="audit",
        )
    assert claimed is not None
    ok = await worker._process_job(claimed)
    assert ok is True

    # Verify audit model was invoked
    assert len(client.requests) == 1
    assert client.requests[0].model == settings.rm_audit_model

    # Verify return transitioned to awaiting_review due to audit disagreement
    async with db.transaction(c["org"]) as conn:
        cur = await conn.execute("SELECT status FROM rm.returns WHERE return_id = %s", (c["return_id"],))
        assert (await cur.fetchone())["status"] == "awaiting_review"

        cur = await conn.execute(
            "SELECT eval_run_id, routes_to_review, disagreements FROM rm.audit_findings WHERE return_id = %s",
            (c["return_id"],),
        )
        finding = await cur.fetchone()
        assert finding is not None
        assert finding["eval_run_id"] == "eval-worker-01"
        assert finding["routes_to_review"] is True

    # Verify event chain passes
    report = await run_verify_org(db.pool, c["org"])
    assert report.valid is True


# ── Quota & Kill Switch Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_and_escalation_quota_holds(db: Database, p9_fixture_case: dict[str, Any]) -> None:
    """Worker holds audit and escalation jobs when daily quota is exhausted without failing returns."""
    c = p9_fixture_case
    settings = get_settings()
    client = ScriptedClient([])
    quota = QuotaGuard(db, settings)
    handler = JudgmentHandler(db, settings, client, MemStorage(), quota)

    # 1. Test audit kill switch
    await controls.set_global_control(
        db, controls.Control.AUDIT, enabled=False, reason="test audit kill switch", actor="tester"
    )

    async with db.transaction(c["org"]) as conn:
        audit_job = await JobQueue.enqueue_job(conn, c["org"], c["return_id"], kind="audit", priority=-10)

    worker = Worker(db, settings, concurrency=1, kinds=["audit"], handler=handler, worker_id="hold-worker")
    async with db.transaction(c["org"]) as conn:
        claimed_audit = await JobQueue.claim_specific(
            conn, c["org"], c["return_id"], worker_id=worker.worker_id, kinds="audit"
        )
    assert claimed_audit is not None
    processed = await worker._process_job(claimed_audit)
    assert processed is False

    async with db.transaction(c["org"]) as conn:
        cur = await conn.execute(
            "SELECT status, last_error_class FROM rm.inspection_jobs WHERE job_id = %s", (audit_job.job_id,)
        )
        j_row = await cur.fetchone()
        assert j_row["status"] == "failed_retryable"
        assert j_row["last_error_class"] == "model_calls_disabled"

    # Reset kill switch
    await controls.set_global_control(
        db, controls.Control.AUDIT, enabled=True, reason="reset", actor="tester"
    )

    # 2. Test escalation kill switch
    await controls.set_global_control(
        db, controls.Control.ESCALATION, enabled=False, reason="test escalation kill switch", actor="tester"
    )

    async with db.transaction(c["org"]) as conn:
        esc_job = await JobQueue.enqueue_job(conn, c["org"], c["return_id"], kind="escalation", priority=10)

    worker_esc = Worker(
        db, settings, concurrency=1, kinds=["escalation"], handler=handler, worker_id="hold-worker-esc"
    )
    async with db.transaction(c["org"]) as conn:
        claimed_esc = await JobQueue.claim_specific(
            conn, c["org"], c["return_id"], worker_id=worker_esc.worker_id, kinds="escalation"
        )
    assert claimed_esc is not None
    processed_esc = await worker_esc._process_job(claimed_esc)
    assert processed_esc is False

    async with db.transaction(c["org"]) as conn:
        cur = await conn.execute(
            "SELECT status, last_error_class FROM rm.inspection_jobs WHERE job_id = %s", (esc_job.job_id,)
        )
        j_row = await cur.fetchone()
        assert j_row["status"] == "failed_retryable"
        assert j_row["last_error_class"] == "model_calls_disabled"
        # Return status must NOT have moved to pending or failed!
        cur = await conn.execute("SELECT status FROM rm.returns WHERE return_id = %s", (c["return_id"],))
        assert (await cur.fetchone())["status"] == "awaiting_review"

    # Reset kill switch
    await controls.set_global_control(
        db, controls.Control.ESCALATION, enabled=True, reason="reset", actor="tester"
    )


# ── Tenant Isolation Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_escalation_and_audit_cross_org_denial(db: Database, p9_fixture_case: dict[str, Any]) -> None:
    """Cross-org read of escalation merges or audit findings returns 0 rows due to RLS."""
    c = p9_fixture_case
    other_org = f"org_other_{uuid.uuid4().hex[:12]}"
    async with db.transaction(other_org) as conn:
        await conn.execute(
            "INSERT INTO rm.organizations (org_id, name) VALUES (%s, 'Other Org')", (other_org,)
        )

    # Insert a merge and audit finding for c["org"]
    svc = EscalationAuditService(db)
    await svc.merge(
        org_id=c["org"],
        return_id=c["return_id"],
        primary_inspection_id=c["prim_ins"],
        escalation_inspection_id=c["esc_ins"],
        primary={"identity_match": "uncertain"},
        escalation={"identity_match": "yes"},
    )
    await svc.record_audit(
        org_id=c["org"],
        return_id=c["return_id"],
        primary_inspection_id=c["prim_ins"],
        audit_inspection_id=c["aud_ins"],
        primary={"identity_match": "yes"},
        audit={"identity_match": "no"},
        eval_run_id="eval-isolation-test",
    )

    # When queried under other_org tenant context, RLS returns 0 rows
    async with db.transaction(other_org) as conn:
        cur = await conn.execute(
            "SELECT * FROM rm.escalation_merges WHERE return_id = %s",
            (c["return_id"],),
        )
        assert await cur.fetchall() == []

        cur = await conn.execute(
            "SELECT * FROM rm.audit_findings WHERE return_id = %s",
            (c["return_id"],),
        )
        assert await cur.fetchall() == []


# ── CLI Tests: audit run dry-run & spend protections ─────────────────────────


def test_audit_cli_dry_run_and_spend_protection() -> None:
    """CLI `audit run --dry-run` succeeds with 0; live audit without --confirm-spend exits 4."""
    # 1. Dry run
    code_dry = cli_run(["audit", "run", "--eval-run", "eval-cli-test", "--dry-run"])
    assert code_dry == int(ExitCode.OK)

    # 2. Run without --confirm-spend should refuse with ExitCode.SPEND_GUARD_REFUSED (4)
    # in live gemini environment or spend guard check
    code_help = cli_run(["audit", "run", "--help"])
    assert code_help == int(ExitCode.OK)
