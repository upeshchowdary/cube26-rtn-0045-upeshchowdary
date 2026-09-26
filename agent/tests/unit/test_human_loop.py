"""P8/P9 acceptance tests: preserved overrides, four-eyes, supersession, and merge rows."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio

from returns_manager.chain.service import run_verify_org
from returns_manager.errors import Conflict
from returns_manager.review.escalation_service import EscalationAuditService
from returns_manager.review.merge import audit_disagreements, audit_sampled, merge_area
from returns_manager.review.service import HumanReviewService, OverrideInput

pytestmark = pytest.mark.db


@pytest_asyncio.fixture()
async def decision_case(db: Any) -> tuple[str, str, str]:
    org = f"org_review_{uuid.uuid4().hex[:12]}"
    unit = f"UNIT-RVW-{uuid.uuid4().hex[:8]}"
    order = f"ORD-RVW-{uuid.uuid4().hex[:8]}"
    ret = f"ret-rvw-{uuid.uuid4().hex[:12]}"
    inspection = f"ins-rvw-{uuid.uuid4().hex[:12]}"
    record = f"RTN-{uuid.uuid4().int % 9000 + 1000:04d}"
    async with db.transaction(org) as conn:
        await conn.execute("INSERT INTO rm.organizations (org_id, name) VALUES (%s, 'review test')", (org,))
        await conn.execute(
            """INSERT INTO rm.orders (
                 org_id, order_id, unit_id, ordered_sku, quantity, fulfilment_route, ordered_at
               )
               VALUES (%s, %s, %s, 'SKU-LAMP-LED', 1, 'fba', now())""",
            (org, order, unit),
        )
        await conn.execute(
            """INSERT INTO rm.returns (
                 return_id, org_id, record_id, unit_id, order_id, return_seq, created_by, status
               )
               VALUES (%s, %s, %s, %s, %s, 1, 'capturer', 'awaiting_operator')""",
            (ret, org, record, unit, order),
        )
        await conn.execute(
            """INSERT INTO rm.inspection_runs (
                 inspection_id, org_id, return_id, kind, status, context_manifest
               )
               VALUES (%s, %s, %s, 'judgment', 'completed', '{}'::jsonb)""",
            (inspection, org, ret),
        )
        await conn.execute(
            """INSERT INTO rm.inspection_results (
                 result_id, org_id, return_id, inspection_id, identity_match, fused_identity, unit_presence,
                 completeness_status, components, amazon_condition, condition, claim_signals, uncertainties,
                 retake_requests, validator_actions, checks, escalation_state, recommended_disposition,
                 provisional, disposition, disposition_inputs, requires_review,
                 review_reasons, requires_signoff
               ) VALUES (
                 %s, %s, %s, %s, 'yes', '{}'::jsonb, 'product_present', 'complete', '[]'::jsonb,
                 'Used - Good', '{}'::jsonb, '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                 '[]'::jsonb, 'not_triggered', 'restock', false,
                 '{"recommended_disposition":"restock","rule_id":"R13"}'::jsonb,
                 '{}'::jsonb, false, '{}', false
               )""",
            (f"res-{uuid.uuid4().hex[:12]}", org, ret, inspection),
        )
        escalation = f"esc-rvw-{uuid.uuid4().hex[:12]}"
        audit = f"aud-rvw-{uuid.uuid4().hex[:12]}"
        for inspection_id, kind in ((escalation, "escalation"), (audit, "audit")):
            await conn.execute(
                """INSERT INTO rm.inspection_runs (
                     inspection_id, org_id, return_id, kind, status, context_manifest
                   ) VALUES (%s, %s, %s, %s, 'completed', '{}'::jsonb)""",
                (inspection_id, org, ret, kind),
            )
    return org, ret, unit, inspection, escalation, audit


@pytest.mark.asyncio
async def test_override_is_preserved_and_post_finalization_creates_superseding_record(
    db: Any, decision_case: tuple[str, str, str, str, str, str]
) -> None:
    """P8: old record remains available, new override version is chain-valid."""
    org, ret, _, _, _, _ = decision_case
    svc = HumanReviewService(db)
    first = await svc.decide(
        org_id=org, actor_id="capturer", actor_role="operator", return_id=ret, action="accept"
    )
    assert first.status == "finalized"
    assert first.record_version == 1
    second = await svc.decide(
        org_id=org,
        actor_id="capturer",
        actor_role="operator",
        return_id=ret,
        action="override",
        overrides=[
            OverrideInput("disposition", "liquidate", "policy_exception", "approved business exception")
        ],
    )
    assert second.status == "finalized"
    assert second.record_version == 2
    async with db.transaction(org) as conn:
        cur = await conn.execute(
            """SELECT status FROM rm.evidence_records
               WHERE org_id = %s AND return_id = %s ORDER BY record_version""",
            (org, ret),
        )
        assert [r["status"] for r in await cur.fetchall()] == ["superseded", "finalized"]
        cur = await conn.execute(
            "SELECT field_path, new_value FROM rm.overrides WHERE org_id = %s AND return_id = %s", (org, ret)
        )
        row = await cur.fetchone()
        assert row["field_path"] == "disposition"
        assert row["new_value"] == "liquidate"
    verified = await run_verify_org(db, org)
    assert verified.valid, verified.failures


@pytest.mark.asyncio
async def test_finalized_document_conforms_to_the_evidence_contract(
    db: Any, decision_case: tuple[str, str, str, str, str, str]
) -> None:
    """P8/P10: a document produced by the real decide() -> _finalize_document() path
    (not a hand-crafted contract-shaped fixture) must validate as an EvidenceRecord
    and carry real data through to the fixed top-level fields and extensions.returns."""
    from returns_manager.contract.models import EvidenceRecord
    from returns_manager.contract.service import get_evidence_document

    org, ret, unit, _, _, _ = decision_case
    svc = HumanReviewService(db)
    decision = await svc.decide(
        org_id=org,
        actor_id="capturer",
        actor_role="operator",
        return_id=ret,
        action="override",
        overrides=[OverrideInput("disposition", "liquidate", "policy_exception", "approved exception")],
    )
    assert decision.status == "finalized"

    doc = await get_evidence_document(db.pool, org_id=org, unit_id=unit)
    assert doc is not None
    record = EvidenceRecord.model_validate(doc)

    assert record.organization_id == org
    assert record.subject["unit_id"] == unit
    assert record.subject["order_id"]
    assert record.status == "finalized"
    assert record.content_hash.startswith("sha256:")
    assert record.outcome.decision == "LIQUIDATE"
    assert record.outcome.decided_by == "operator:capturer"

    ext = record.extensions["returns"]
    assert ext["unit_id"] == unit
    assert ext["disposition"]["rule_id"] == "R13"
    assert ext["disposition"]["final_disposition"] == "liquidate"
    assert ext["disposition"]["recommended_disposition"] == "liquidate"
    assert len(ext["overrides"]) == 1
    assert ext["overrides"][0]["by"] == "operator:capturer"


@pytest.mark.asyncio
async def test_four_eyes_blocks_capturer_and_finalizes_after_independent_approval(
    db: Any, decision_case: tuple[str, str, str, str, str, str]
) -> None:
    org, ret, _, _, _, _ = decision_case
    svc = HumanReviewService(db)
    await svc.decide(
        org_id=org,
        actor_id="capturer",
        actor_role="operator",
        return_id=ret,
        action="override",
        overrides=[OverrideInput("disposition", "dispose", "missed_defect", "unsafe damage confirmed")],
    )
    with pytest.raises(Conflict, match="Four-eyes"):
        await svc.signoff(org_id=org, reviewer_id="capturer", return_id=ret, approved=True, reason="self")
    final = await svc.signoff(
        org_id=org, reviewer_id="reviewer-2", return_id=ret, approved=True, reason="checked"
    )
    assert final.status == "finalized"
    assert final.record_version == 1


def test_escalation_merge_table_and_blind_audit_rules() -> None:
    assert merge_area("uncertain", "yes").outcome == "resolved_by_escalation"
    assert merge_area("yes", "yes").outcome == "kept_primary"
    conflict = merge_area("yes", "no")
    assert conflict.value == "uncertain"
    assert conflict.requires_review
    assert merge_area("yes", "uncertain").outcome == "uncertain"
    assert audit_sampled("RTN-0001", 0.0) is False
    assert audit_sampled("RTN-0001", 0.0, eval_run=True) is True
    assert audit_sampled("RTN-0001", 1.0) is True
    assert audit_disagreements(
        {
            "identity_match": "yes",
            "completeness_status": "complete",
            "unit_presence": "product_present",
            "cosmetic_grade": "new",
        },
        {
            "identity_match": "no",
            "completeness_status": "complete",
            "unit_presence": "product_present",
            "cosmetic_grade": "used_good",
        },
    ) == ("identity_match", "cosmetic_grade")


@pytest.mark.asyncio
async def test_escalation_merge_and_audit_are_append_only_and_route_open_case_to_review(
    db: Any, decision_case: tuple[str, str, str, str, str, str]
) -> None:
    org, ret, _, primary_id, escalation_id, audit_id = decision_case
    svc = EscalationAuditService(db)
    merged = await svc.merge(
        org_id=org,
        return_id=ret,
        primary_inspection_id=primary_id,
        escalation_inspection_id=escalation_id,
        primary={"identity_match": "uncertain", "unit_presence": "product_present"},
        escalation={"identity_match": "yes", "unit_presence": "product_present"},
    )
    assert merged["identity_match"]["outcome"] == "resolved_by_escalation"
    disagreements = await svc.record_audit(
        org_id=org,
        return_id=ret,
        primary_inspection_id=primary_id,
        audit_inspection_id=audit_id,
        primary={
            "identity_match": "yes",
            "completeness_status": "complete",
            "unit_presence": "product_present",
            "cosmetic_grade": "new",
        },
        audit={
            "identity_match": "no",
            "completeness_status": "complete",
            "unit_presence": "product_present",
            "cosmetic_grade": "used_good",
        },
    )
    assert disagreements == ("identity_match", "cosmetic_grade")
    async with db.transaction(org) as conn:
        cur = await conn.execute(
            "SELECT count(*) AS count FROM rm.escalation_merges WHERE org_id = %s", (org,)
        )
        assert (await cur.fetchone())["count"] == 2
        cur = await conn.execute("SELECT routes_to_review FROM rm.audit_findings WHERE org_id = %s", (org,))
        assert (await cur.fetchone())["routes_to_review"] is True
        cur = await conn.execute(
            "SELECT status FROM rm.returns WHERE org_id = %s AND return_id = %s", (org, ret)
        )
        assert (await cur.fetchone())["status"] == "awaiting_review"
