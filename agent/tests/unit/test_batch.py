"""Standalone batch pipeline (CSV + image-URL import, no database): pure-logic tests.

Network and live-model paths (`images.fetch_image`, `runner.run_batch`) are exercised
manually against real hosted photos, per build-log; they are not repeated here as replay
cassettes do not exist for this ad hoc path.
"""

from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from returns_manager.batch.cards import VALID_CATEGORIES, build_card
from returns_manager.batch.images import USER_AGENT, fetch_image
from returns_manager.batch.io_csv import (
    BeforeRow,
    ReturnedRow,
    read_before_csv,
    read_returned_csv,
    write_output_csv,
)
from returns_manager.batch.jobs_service import BatchJob, BatchJobsService
from returns_manager.batch.parts import parse_parts_list
from returns_manager.batch.runner import (
    _build_row_detail,
    _id_mismatch,
    _is_auto_disapproved,
    _missing_parts_field,
    _operator_disposition,
    _uncertain_row,
    check_id_match,
)
from returns_manager.config import Settings
from tests.unit import judgment_builders as b


async def test_fetch_image_sends_repository_user_agent() -> None:
    requested: dict[str, Any] = {}
    image_bytes = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(image_bytes, format="JPEG")

    class Response:
        status_code = 200
        content = image_bytes.getvalue()

    class Client:
        async def get(self, url: str, **kwargs: Any) -> Response:
            requested.update(url=url, **kwargs)
            return Response()

    result = await fetch_image("https://upload.wikimedia.org/example.jpg", Client(), long_edge=10)

    assert result
    assert requested["headers"] == {"User-Agent": USER_AGENT}
    assert requested["follow_redirects"] is True


# ── parts_list parsing and essential/replaceable classification ──────────────────────


def test_parse_parts_list_first_part_is_root_non_replaceable() -> None:
    parts = parse_parts_list("lamp;usb cable;manual")
    assert [p.name for p in parts] == ["lamp", "usb cable", "manual"]
    assert parts[0].essential
    assert not parts[0].replaceable
    assert all(p.replaceable for p in parts[1:])
    # directive 5: a standard cable or a manual is a cheap, non-essential accessory
    assert not parts[1].essential
    assert not parts[2].essential
    assert parse_parts_list("laptop;charger")[1].essential  # a charger is needed to use the unit


def test_parse_parts_list_quantity_suffix() -> None:
    parts = parse_parts_list("candle x3;gift box")
    assert parts[0].name == "candle"
    assert parts[0].quantity == 3
    assert parts[1].name == "gift box"
    assert parts[1].quantity == 1


def test_parse_parts_list_single_part_is_root() -> None:
    parts = parse_parts_list("mug x2")
    assert len(parts) == 1
    assert parts[0].essential
    assert not parts[0].replaceable


def test_parse_parts_list_empty_string() -> None:
    assert parse_parts_list("") == []
    assert parse_parts_list("   ") == []


def test_parse_parts_list_ids_are_unique_slugs() -> None:
    parts = parse_parts_list("Bottle;Bottle;lid")
    ids = [p.component_id for p in parts]
    assert len(ids) == len(set(ids))
    assert all(i.islower() or i.isdigit() or "_" in i for i in ids)


# ── card synthesis ─────────────────────────────────────────────────────────────────


def test_build_card_matches_parts_essential_replaceable() -> None:
    parts = parse_parts_list("bottle;lid")
    card = build_card(
        org_id="org_demo_alpha",
        sku="SKU-BOTTLE-750",
        asin="B0DUMMY622",
        category_key="home_kitchen",
        parts=parts,
    )
    by_name = {c.name: c for c in card.components}
    assert by_name["bottle"].essential is True
    assert by_name["bottle"].replaceable is False
    assert by_name["lid"].essential is True
    assert by_name["lid"].replaceable is True
    assert card.value.synthetic is True
    assert card.reference_images == []


def test_build_card_falls_back_to_main_unit_when_no_parts_given() -> None:
    card = build_card(org_id="org_demo_alpha", sku="SKU-X", asin=None, category_key="electronics", parts=[])
    assert len(card.components) == 1
    assert card.components[0].essential is True
    assert card.components[0].replaceable is False


def test_valid_categories_match_existing_reference_directories() -> None:
    # Every category the batch tool accepts must have both a rubric and a policy file, or
    # a synthesized card would point run_batch at reference data that does not exist.
    repo_root = Path(__file__).resolve().parents[3]
    for cat in VALID_CATEGORIES:
        assert (repo_root / "reference" / "rubrics" / "amazon.co.uk" / f"{cat}.yaml").is_file()
        assert (repo_root / "reference" / "policies" / "amazon.co.uk" / f"{cat}.yaml").is_file()


# ── CSV I/O and join ───────────────────────────────────────────────────────────────


def test_read_before_csv_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "before.csv"
    path.write_text(
        "record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,identity_match,parts_list,time,"
        "photo_ref,category\n"
        "PCK-1,UNIT-1,org_demo_alpha,ORD-1,SKU-A,ASIN-A,yes,handset;battery,2026-01-01T00:00:00Z,"
        "https://example.com/ref.jpg,electronics\n",
        encoding="utf-8",
    )
    by_unit = read_before_csv(path)
    assert set(by_unit) == {"UNIT-1"}
    row = by_unit["UNIT-1"]
    assert row.parts_list == "handset;battery"
    assert row.category == "electronics"
    assert row.photo_ref == "https://example.com/ref.jpg"


def test_read_before_csv_missing_column_raises(tmp_path: Path) -> None:
    path = tmp_path / "before.csv"
    path.write_text("record_id,unit_id\nPCK-1,UNIT-1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required column"):
        read_before_csv(path)


def test_read_returned_csv_splits_multiple_photo_refs(tmp_path: Path) -> None:
    path = tmp_path / "returned.csv"
    path.write_text(
        "record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,returned_photo_ref,time\n"
        "RTN-1,UNIT-1,org_demo_alpha,ORD-1,SKU-A,ASIN-A,"
        "https://example.com/a.jpg;https://example.com/b.jpg,2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    rows = read_returned_csv(path)
    assert len(rows) == 1
    assert rows[0].returned_photo_refs == ("https://example.com/a.jpg", "https://example.com/b.jpg")


def test_write_output_csv_uses_fixed_column_order(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    write_output_csv(
        out,
        [
            {
                "record_id": "RTN-1",
                "unit_id": "UNIT-1",
                "org_id": "org_demo_alpha",
                "order_id": "ORD-1",
                "ordered_sku": "SKU-A",
                "ordered_asin": "ASIN-A",
                "identity_match": "yes",
                "parts_list": "handset;battery",
                "parts_missing": "battery",
                "observed_state": "damaged",
                "amazon_condition": "Used - Good",
                "operator_disposition": "liquidate",
                "photo_refs": "https://example.com/a.jpg",
                "captured_at": "2026-01-01T00:00:00Z",
                "sold_vs_returned_id_check": "matched",
                # extra keys must be ignored, never leak a new column into the sample shape
                "unexpected_extra": "should not appear",
            }
        ],
    )
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert header == (
        "record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,identity_match,photo_identity_match,"
        "parts_list,parts_missing,observed_state,amazon_condition,operator_disposition,agent_disposition,"
        "auto_approved,auto_disapproved,photo_refs,captured_at,sold_vs_returned_id_check,failure_reason,value_source,"
        "requires_review,rationale"
    )
    assert "unexpected_extra" not in out.read_text(encoding="utf-8")


# ── row-level fail-open output shape ───────────────────────────────────────────────


def test_uncertain_row_carries_forward_identity_and_parts_when_before_known() -> None:
    row = ReturnedRow(
        record_id="RTN-1",
        unit_id="UNIT-1",
        org_id="org_demo_alpha",
        order_id="ORD-1",
        ordered_sku="SKU-A",
        ordered_asin="ASIN-A",
        returned_photo_refs=("https://example.com/a.jpg",),
        time="2026-01-01T00:00:00Z",
    )
    before_row = BeforeRow(
        record_id="PCK-1",
        unit_id="UNIT-1",
        org_id="org_demo_alpha",
        order_id="ORD-1",
        ordered_sku="SKU-A",
        ordered_asin="ASIN-A",
        identity_match="yes",
        parts_list="handset;battery",
        time="2026-01-01T00:00:00Z",
        photo_ref="https://example.com/ref.jpg",
        category="electronics",
    )
    out = _uncertain_row(row, before_row, "image_fetch_failed: timeout")
    assert out["identity_match"] == "yes"
    assert out["parts_list"] == "handset;battery"
    assert out["observed_state"] == "uncertain"
    assert out["operator_disposition"] == "pending_review"
    assert out["parts_missing"] == ""
    assert out["sold_vs_returned_id_check"] == "matched"
    assert out["failure_reason"] == "image_fetch_failed: timeout"
    assert out["photo_identity_match"] == "uncertain"
    assert out["auto_disapproved"] == "false"


def test_uncertain_row_without_before_record_leaves_identity_blank() -> None:
    """No before-record means there is no identity_match to carry forward: blank, not an invented
    "uncertain". (Replaces test_uncertain_row_without_before_record_defaults_to_uncertain_identity,
    which asserted that invented default.)"""
    row = ReturnedRow(
        record_id="RTN-1",
        unit_id="UNIT-404",
        org_id="org_demo_alpha",
        order_id="ORD-1",
        ordered_sku="SKU-A",
        ordered_asin="ASIN-A",
        returned_photo_refs=("https://example.com/a.jpg",),
        time="2026-01-01T00:00:00Z",
    )
    out = _uncertain_row(row, None, "no before-record for this unit_id")
    assert out["identity_match"] == ""
    assert out["parts_list"] == ""
    assert out["operator_disposition"] == "pending_review"
    assert out["sold_vs_returned_id_check"] == "NOT MATCHED: no sold-record for this unit_id"


# ── sold-record vs returned-record ID consistency check ────────────────────────────
# A returned package can carry the wrong order/SKU/org/ASIN on its own label even when
# the photo inside it is completely genuine - a photo-based identity match can't catch
# that, so this is a separate, plain data comparison between the two records.


def _before(**overrides: Any) -> BeforeRow:
    base = dict(
        record_id="PCK-1",
        unit_id="UNIT-1",
        org_id="org_demo_alpha",
        order_id="ORD-1",
        ordered_sku="SKU-A",
        ordered_asin="ASIN-A",
        identity_match="yes",
        parts_list="handset;battery",
        time="2026-01-01T00:00:00Z",
        photo_ref="https://example.com/ref.jpg",
        category="electronics",
    )
    base.update(overrides)
    return BeforeRow(**base)


def _returned(**overrides: Any) -> ReturnedRow:
    base = dict(
        record_id="RTN-1",
        unit_id="UNIT-1",
        org_id="org_demo_alpha",
        order_id="ORD-1",
        ordered_sku="SKU-A",
        ordered_asin="ASIN-A",
        returned_photo_refs=("https://example.com/a.jpg",),
        time="2026-01-01T00:00:00Z",
    )
    base.update(overrides)
    return ReturnedRow(**base)  # type: ignore[arg-type]


def test_check_id_match_all_ids_agree() -> None:
    assert check_id_match(_before(), _returned()) == "matched"


def test_check_id_match_no_sold_record() -> None:
    assert check_id_match(None, _returned()) == "NOT MATCHED: no sold-record for this unit_id"


def test_check_id_match_flags_order_id_mismatch() -> None:
    result = check_id_match(_before(), _returned(order_id="ORD-999"))
    assert result.startswith("NOT MATCHED:")
    assert "order_id" in result
    assert "ORD-1" in result
    assert "ORD-999" in result


def test_check_id_match_flags_sku_and_asin_mismatch_together() -> None:
    result = check_id_match(_before(), _returned(ordered_sku="SKU-B", ordered_asin="ASIN-B"))
    assert result.startswith("NOT MATCHED:")
    assert "ordered_sku" in result
    assert "ordered_asin" in result
    assert "org_id" not in result
    assert "order_id" not in result


def test_check_id_match_flags_org_id_mismatch() -> None:
    result = check_id_match(_before(), _returned(org_id="org_demo_beta"))
    assert result.startswith("NOT MATCHED:")
    assert "org_id" in result


# ── four dispositions only (B3, §12.2) ─────────────────────────────────────────────
# A mismatched order/SKU/org/ASIN on the returned label outranks whatever the photo looked
# like, so it holds the row for review - as a review flag, never as a fifth disposition. A
# wrong item seen by the model is §12.2 R03: recommended_disposition=None with
# no_recommendation_reason=wrong_item_returned, and the row is pending_review.
# (These replace three tests that asserted the former `wrong_product` value.)

DISPOSITIONS = {"restock", "refurbish", "liquidate", "dispose"}


def test_uncertain_row_on_id_mismatch_is_pending_review_not_a_fifth_disposition() -> None:
    row = _returned(order_id="ORD-999")
    out = _uncertain_row(row, _before(), "image_fetch_failed: timeout")
    assert out["operator_disposition"] == "pending_review"
    assert out["sold_vs_returned_id_check"].startswith("NOT MATCHED:")
    assert out["auto_disapproved"] == "true"


def test_auto_disapproval_requires_a_proven_id_or_image_mismatch() -> None:
    assert _is_auto_disapproved(_before(), _returned(order_id="ORD-999"), "uncertain") is True
    assert _is_auto_disapproved(_before(), _returned(), "no") is True
    assert _is_auto_disapproved(_before(), _returned(), "uncertain") is False
    assert _is_auto_disapproved(None, _returned(), "uncertain") is False


def test_auto_disapproval_never_triggers_on_damaged_or_uncertain_identity() -> None:
    # A damaged return of the sold item is NOT an automatic disapproval (wrong product rejection);
    # it routes to review / refurbish / salvage.
    assert _is_auto_disapproved(_before(), _returned(), "yes") is False
    assert _is_auto_disapproved(_before(), _returned(), "uncertain") is False


def test_uncertain_row_no_sold_record_stays_pending_review() -> None:
    out = _uncertain_row(_returned(), None, "no before-record for this unit_id")
    assert out["operator_disposition"] == "pending_review"
    assert out["sold_vs_returned_id_check"] == "NOT MATCHED: no sold-record for this unit_id"


def test_operator_disposition_is_a_route_or_pending_review_only() -> None:
    assert _operator_disposition("restock", auto_approved=True) == "restock"
    assert _operator_disposition("restock", auto_approved=False) == "pending_review"
    assert _operator_disposition(None, auto_approved=True) == "pending_review"
    assert _id_mismatch(_before(), "NOT MATCHED: order_id: ...") is True
    assert _id_mismatch(_before(), "matched") is False
    assert _id_mismatch(None, "NOT MATCHED: no sold-record for this unit_id") is False
    for route in DISPOSITIONS:
        assert _operator_disposition(route, auto_approved=True) in DISPOSITIONS


def test_wrong_item_is_r03_dispose_with_signoff_and_pending_review() -> None:
    from returns_manager.llm.schemas import JudgmentV1

    ctx = b.context(b.headphones_card())
    raw = b.judgment(ctx).model_dump(mode="json")
    raw["identity"]["identity_match"] = "no"
    for fc in raw["identity"]["feature_checks"]:
        fc["result"] = "mismatch"
    result = b.run(ctx, JudgmentV1.model_validate(raw))

    assert result.decision.rule_id == "R03"
    # directive 3: never null for a confirmed wrong item; dispose always keeps its human sign-off
    assert result.decision.recommended_disposition == "dispose"
    assert "S01_dispose_always" in result.decision.signoff_reasons
    assert "wrong_item_returned" in result.decision.review_reasons
    assert result.claims.wrong_item_returned.value == "yes"
    # it can never be auto-approved, so the operator column stays pending_review until a person signs off
    from returns_manager.batch import auto_approve

    assert not auto_approve.evaluate(result, id_mismatch=False, id_not_checked=False, threshold_bp=0).approved


@pytest.mark.parametrize("value", ["wrong_product", "pending_review", "RESTOCK", "return_to_vendor"])
def test_decision_request_rejects_anything_but_the_four_dispositions(value: str) -> None:
    from pydantic import ValidationError

    from returns_manager.api.routes.batch import RowDecisionRequest

    with pytest.raises(ValidationError):
        RowDecisionRequest(action="override", new_disposition=value, reason="r")  # type: ignore[arg-type]
    for route in DISPOSITIONS:
        assert (
            RowDecisionRequest(action="override", new_disposition=route, reason="r").new_disposition == route
        )  # type: ignore[arg-type]


def test_flat_contract_enumerates_only_the_four_dispositions() -> None:
    from returns_manager.contract.schema import generate_flat_schema

    props = generate_flat_schema()["properties"]
    assert set(props["operator_disposition"]["enum"]) == DISPOSITIONS | {"pending_review"}
    assert set(props["agent_disposition"]["enum"]) == DISPOSITIONS | {""}
    committed = json.loads(
        (Path(__file__).resolve().parents[2] / "contract" / "return-evidence-flat.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert committed["properties"]["operator_disposition"] == props["operator_disposition"]


def test_committed_example_output_csv_uses_only_the_four_dispositions() -> None:
    import csv

    path = Path(__file__).resolve().parents[2] / "manual_test_images" / "returns_output_30.csv"
    with path.open(encoding="utf-8") as f:
        values = {r["operator_disposition"] for r in csv.DictReader(f)}
    assert values <= DISPOSITIONS | {"pending_review"}, values


class _FakeCompleteness:
    def __init__(self, missing: str, uncertain: str) -> None:
        self.parts_missing = missing
        self.parts_uncertain = uncertain


def test_missing_parts_field_lists_only_confirmed_missing_parts() -> None:
    # a part that is merely not visible is never reported as missing
    assert _missing_parts_field(_FakeCompleteness("battery", "battery;battery cover")) == "battery"
    assert _missing_parts_field(_FakeCompleteness("", "charger")) == ""
    assert _missing_parts_field(_FakeCompleteness("", "")) == ""
    assert _missing_parts_field(_FakeCompleteness("lid", "")) == "lid"


# ── rich per-row detail (§14.2 checks + identity/completeness/condition/decision) ──
# The UI's inspection detail view reads this JSON directly - it must not silently
# discard the pydantic `judgment` field the way a bare `dataclasses.asdict(result)`
# would (asdict does not know how to flatten a nested pydantic BaseModel).


def test_build_row_detail_is_json_serializable_and_carries_real_pipeline_fields() -> None:
    ctx = b.context(b.headphones_card())
    j = b.component(
        ctx, b.judgment(ctx), "usb_cable", status="missing", visibility="observed_absent_in_clear_view"
    )
    j = b.grade(j, "used_good", ctx)
    result = b.run(ctx, j)
    row = _returned(returned_photo_refs=("https://example.com/a.jpg", "https://example.com/b.jpg"))
    before = _before(photo_ref="https://example.com/ref.jpg")

    detail = _build_row_detail(session_judgment=j, result=result, row=row, before=before)
    # Must round-trip through the exact encoder the API route uses (plain json.dumps, no
    # custom default=) - a live pydantic object anywhere in the tree would raise here.
    decoded = json.loads(json.dumps(detail))

    assert decoded["decision"]["rule_id"] == result.decision.rule_id
    assert decoded["decision"]["recommended_disposition"] == "refurbish"
    assert {c["check_key"] for c in decoded["checks"]} >= {"identity", "completeness", "condition_grade"}
    assert decoded["identity"]["identity_match"] == "yes"
    assert decoded["completeness"]["parts_missing"] == "usb cable"
    assert decoded["condition"]["amazon_condition"] == "Used - Good"
    assert decoded["judgment"]["schema_version"] == "judgment/v1"
    assert decoded["judgment_raw"]["schema_version"] == "judgment/v1"
    assert decoded["returned_photo_refs"] == ["https://example.com/a.jpg", "https://example.com/b.jpg"]
    assert decoded["reference_photo_ref"] == "https://example.com/ref.jpg"


# ── filesystem-backed job store: detail lookup and row-level decisions ─────────────


def _service(tmp_path: Path) -> BatchJobsService:
    return BatchJobsService(root=tmp_path / "jobs", settings=Settings.model_construct(), client=None)  # type: ignore[arg-type]


def _done_job(svc: BatchJobsService, org_id: str, job_id: str) -> None:
    job = BatchJob(
        job_id=job_id,
        org_id=org_id,
        status="done",
        created_at=time.time(),
        before_filename="before.csv",
        returned_filename="returned.csv",
    )
    svc._jobs[job_id] = job
    svc._job_dir(org_id, job_id).mkdir(parents=True, exist_ok=True)


def test_output_row_detail_returns_none_for_unknown_row_or_job(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _done_job(svc, "org_demo_alpha", "job-1")
    job_dir = svc._job_dir("org_demo_alpha", "job-1")
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "rows_detail.json").write_text(json.dumps({"RTN-1": {"decision": {"rule_id": "R09"}}}))

    assert svc.output_row_detail("org_demo_alpha", "job-1", "RTN-1") == {"decision": {"rule_id": "R09"}}
    assert svc.output_row_detail("org_demo_alpha", "job-1", "RTN-404") is None
    assert svc.output_row_detail("org_demo_alpha", "no-such-job", "RTN-1") is None
    assert svc.output_row_detail("org_demo_bravo", "job-1", "RTN-1") is None  # cross-org


def test_record_decision_appends_and_get_decisions_reads_history_in_order(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _done_job(svc, "org_demo_alpha", "job-1")

    assert svc.get_decisions("org_demo_alpha", "job-1", "RTN-1") == []  # real answer: no decisions yet
    assert svc.get_decisions("org_demo_alpha", "no-such-job", "RTN-1") is None  # vs. job doesn't exist

    first = svc.record_decision(
        "org_demo_alpha",
        "job-1",
        "RTN-1",
        action="review_request",
        new_disposition=None,
        reason="label is blurry",
        actor="user:op_alex",
    )
    second = svc.record_decision(
        "org_demo_alpha",
        "job-1",
        "RTN-1",
        action="override",
        new_disposition="refurbish",
        reason="found the missing cable in a second photo",
        actor="user:rev_priya",
    )
    assert first is not None
    assert second is not None

    history = svc.get_decisions("org_demo_alpha", "job-1", "RTN-1")
    assert history is not None
    assert [d["action"] for d in history] == ["review_request", "override"]
    assert history[1]["new_disposition"] == "refurbish"

    # A decision on a different row of the same job must not appear here.
    svc.record_decision(
        "org_demo_alpha",
        "job-1",
        "RTN-2",
        action="accept",
        new_disposition=None,
        reason="looks right",
        actor="user:op_alex",
    )
    unchanged = svc.get_decisions("org_demo_alpha", "job-1", "RTN-1")
    assert unchanged is not None
    assert len(unchanged) == 2


def test_decision_log_is_hash_chained_and_verifies_tamper(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _done_job(svc, "org_demo_alpha", "job-1")

    first = svc.record_decision(
        "org_demo_alpha",
        "job-1",
        "RTN-1",
        action="review_request",
        new_disposition=None,
        reason="label is blurry",
        actor="user:op_alex",
    )
    assert first is not None
    assert first["prev_hash"]
    assert first["hash"]
    assert svc.verify_decision_log("org_demo_alpha", "job-1")[0] is True

    second = svc.record_decision(
        "org_demo_alpha",
        "job-1",
        "RTN-1",
        action="override",
        new_disposition="refurbish",
        reason="found the missing cable in a second photo",
        actor="user:rev_priya",
    )
    assert second is not None
    assert second["prev_hash"] == first["hash"]
    assert svc.verify_decision_log("org_demo_alpha", "job-1")[0] is True

    history = svc._load_decisions("org_demo_alpha", "job-1")
    history[0]["reason"] = "tampered"
    svc._decisions_path("org_demo_alpha", "job-1").write_text(json.dumps(history), encoding="utf-8")

    valid, problems = svc.verify_decision_log("org_demo_alpha", "job-1")
    assert valid is False
    assert problems
    assert "hash mismatch" in problems[0]


def test_record_decision_on_missing_job_returns_none(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    assert (
        svc.record_decision(
            "org_demo_alpha",
            "no-such-job",
            "RTN-1",
            action="accept",
            new_disposition=None,
            reason="ok",
            actor="user:op_alex",
        )
        is None
    )


def test_render_output_csv_reflects_latest_override_not_the_stored_file(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _done_job(svc, "org_demo_alpha", "job-1")
    write_output_csv(
        svc._job_dir("org_demo_alpha", "job-1") / "output.csv",
        [
            {
                "record_id": "RTN-1",
                "unit_id": "UNIT-1",
                "org_id": "org_demo_alpha",
                "order_id": "ORD-1",
                "ordered_sku": "SKU-A",
                "ordered_asin": "ASIN-A",
                "identity_match": "yes",
                "parts_list": "cable",
                "parts_missing": "cable",
                "observed_state": "signs_of_use",
                "amazon_condition": "Used - Good",
                "operator_disposition": "liquidate",
                "photo_refs": "https://example.com/a.jpg",
                "captured_at": "2026-01-01T00:00:00Z",
                "sold_vs_returned_id_check": "matched",
            }
        ],
    )

    # Before any decision: the download reflects the engine's own original route.
    before_decision = svc.render_output_csv("org_demo_alpha", "job-1")
    assert before_decision is not None
    assert "liquidate" in before_decision.decode("utf-8")

    svc.record_decision(
        "org_demo_alpha",
        "job-1",
        "RTN-1",
        action="override",
        new_disposition="refurbish",
        reason="cable was found",
        actor="user:rev_priya",
    )
    after_override = svc.render_output_csv("org_demo_alpha", "job-1")
    assert after_override is not None
    lines = after_override.decode("utf-8").splitlines()
    assert lines[0] == (
        "record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,identity_match,photo_identity_match,"
        "parts_list,parts_missing,observed_state,amazon_condition,operator_disposition,agent_disposition,"
        "auto_approved,auto_disapproved,photo_refs,captured_at,sold_vs_returned_id_check,failure_reason,value_source,"
        "requires_review,rationale"
    )
    assert "refurbish" in lines[1]
    assert "liquidate" not in after_override.decode("utf-8")

    # A later `accept` confirms the route; it must not silently revert the override.
    svc.record_decision(
        "org_demo_alpha",
        "job-1",
        "RTN-1",
        action="accept",
        new_disposition=None,
        reason="approved",
        actor="user:rev_priya",
    )
    still_refurbish = svc.render_output_csv("org_demo_alpha", "job-1")
    assert still_refurbish is not None
    assert "refurbish" in still_refurbish.decode("utf-8")


def test_render_output_csv_none_when_job_not_done(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    svc._jobs["job-1"] = BatchJob(
        job_id="job-1",
        org_id="org_demo_alpha",
        status="processing",
        created_at=time.time(),
        before_filename="before.csv",
        returned_filename="returned.csv",
    )
    assert svc.render_output_csv("org_demo_alpha", "job-1") is None


def test_split_combined_csv_returns_input_30(tmp_path: Path) -> None:
    from returns_manager.api.routes.batch import _split_combined_csv

    csv_path = Path(__file__).resolve().parents[2] / "manual_test_images" / "returns_input_30.csv"
    if not csv_path.exists():
        pytest.skip("manual_test_images/returns_input_30.csv not found")

    content = csv_path.read_bytes()
    b_bytes, r_bytes = _split_combined_csv(content, csv_path.name)

    b_file = tmp_path / "b.csv"
    r_file = tmp_path / "r.csv"
    b_file.write_bytes(b_bytes)
    r_file.write_bytes(r_bytes)

    before_units = read_before_csv(b_file)
    returned_rows = read_returned_csv(r_file)

    assert len(before_units) == 30
    assert len(returned_rows) == 30
    assert "UNIT-WATCH-01" in before_units
    assert returned_rows[0].unit_id == "UNIT-WATCH-01"
    assert returned_rows[0].ordered_sku == "SKU-WATCH-A"
    assert before_units["UNIT-WATCH-01"].photo_ref.startswith("https://")
    assert len(returned_rows[0].returned_photo_refs) >= 1


# ── fail-open batch honesty (A1/A7) ────────────────────────────────────────────────
# A row that did not get a real model response through the deterministic pipeline comes
# out uncertain / pending_review with its reason, no detail and no confidence number - no
# answer-key replay, no guessing from filenames, URLs, IDs or free-text columns.
# (Replaces the former `test_similarity_confidence_auto_restocks_complete_return`, which
# asserted that a row with identical reference/return photo URLs and NO model call was
# auto-restocked with a fabricated 85%+ "confidence" - the behaviour Rule 3 forbids.)


def _png_bytes() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 130, 140)).save(buf, format="PNG")
    return buf.getvalue()


def _image_client() -> Any:
    import httpx

    png = _png_bytes()
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=png)))


class _NoCallClient:
    """A ModelClient stand-in that fails the test if any request is attempted."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"model client used ({name}) on a path that must not call the model")


def _golden_row(record_id: str) -> tuple[BeforeRow, ReturnedRow]:
    """A before/returned pair for a record_id that exists in the committed answer-key CSV."""
    import csv

    golden = Path(__file__).resolve().parents[2] / "manual_test_images" / "returns_output_30.csv"
    with golden.open(encoding="utf-8") as f:
        g = next(r for r in csv.DictReader(f) if r["record_id"] == record_id)
    photo = "https://example.com/same.jpg"
    before = _before(
        unit_id=g["unit_id"],
        order_id=g["order_id"],
        ordered_sku=g["ordered_sku"],
        ordered_asin=g["ordered_asin"],
        org_id=g["org_id"],
        parts_list=g["parts_list"],
        identity_match="yes",
        photo_ref=photo,
        category="electronics",
    )
    returned = _returned(
        record_id=record_id,
        unit_id=g["unit_id"],
        order_id=g["order_id"],
        ordered_sku=g["ordered_sku"],
        ordered_asin=g["ordered_asin"],
        org_id=g["org_id"],
        returned_photo_refs=(photo,),
    )
    return before, returned


def _assert_fail_open(res: Any, reason: str) -> None:
    out = res.output_row
    assert res.detail is None
    assert res.note == reason
    assert out["failure_reason"] == reason
    assert out["observed_state"] == "uncertain"
    assert out["amazon_condition"] == "uncertain"
    assert out["operator_disposition"] == "pending_review"
    assert out["photo_identity_match"] == "uncertain"
    assert "confidence" not in json.dumps(out).lower()


async def _process(before: BeforeRow, returned: ReturnedRow, quota: Any) -> Any:
    from returns_manager.batch import runner
    from returns_manager.config import get_settings

    async with _image_client() as http:
        return await runner.process_returned_row(
            returned,
            {before.unit_id: before},
            settings=get_settings(),
            client=_NoCallClient(),  # type: ignore[arg-type]
            http_client=http,
            quota=quota,
            default_category=None,
            list_price_minor=100_00,
        )


async def test_quota_exhausted_row_is_pending_review_with_reason_and_no_confidence() -> None:
    from returns_manager.batch.runner import _NoDbQuota

    before, returned = _golden_row("RTN-WATCH-01")
    quota = _NoDbQuota(rpm=60)
    quota.is_exhausted = True
    res = await _process(before, returned, quota)
    _assert_fail_open(res, "model_call_failed:quota_exhausted")
    assert res.attempted_model_call is False


async def test_model_call_failure_is_pending_review_and_answer_key_is_ignored(monkeypatch: Any) -> None:
    """A quota error from the provider mid-run: the row is not replayed from the committed
    answer-key CSV (`manual_test_images/returns_output_30.csv` has an answer for both record_ids),
    and the run's quota is marked exhausted so later rows are not sent either."""
    from returns_manager.batch import runner
    from returns_manager.errors import QuotaExhaustedError
    from returns_manager.llm.loop import SessionFailed, SessionTrace

    async def _quota_fails(*args: Any, **kwargs: Any) -> Any:
        raise SessionFailed(
            QuotaExhaustedError("429 RESOURCE_EXHAUSTED"), SessionTrace(model="m", output_mode="x")
        )

    monkeypatch.setattr(runner, "_run_judgment_with_fallback", _quota_fails)
    for record_id in ("RTN-WATCH-01", "RTN-AIR-02"):  # answer key says restock / wrong_product
        before, returned = _golden_row(record_id)
        quota = runner._NoDbQuota(rpm=60)
        res = await _process(before, returned, quota)
        _assert_fail_open(res, "model_call_failed:quota_exhausted")
        assert res.attempted_model_call is True
        assert quota.is_exhausted is True


async def test_invalid_model_output_with_identical_photo_urls_never_restocks(monkeypatch: Any) -> None:
    """Same reference and return photo URL and matching paperwork - the cues the old heuristic
    turned into an auto-restock - still give no verdict when the model output is invalid."""
    from returns_manager.batch import runner
    from returns_manager.llm.client import SchemaError
    from returns_manager.llm.loop import SessionFailed, SessionTrace

    async def _schema_error(*args: Any, **kwargs: Any) -> Any:
        raise SessionFailed(
            SchemaError("judgment did not validate"), SessionTrace(model="m", output_mode="x")
        )

    monkeypatch.setattr(runner, "_run_judgment_with_fallback", _schema_error)
    before, returned = _golden_row("RTN-WATCH-01")
    res = await _process(before, returned, runner._NoDbQuota(rpm=60))
    assert res.output_row["operator_disposition"] == "pending_review"
    assert res.output_row["failure_reason"].startswith("model_call_failed:")
    _assert_fail_open(res, res.output_row["failure_reason"])


@pytest.mark.parametrize(
    ("before_overrides", "returned_overrides", "reason"),
    [
        ({"photo_ref": ""}, {}, "no_reference_photo"),
        ({}, {"returned_photo_refs": ()}, "no_return_photo"),
        ({"category": None}, {}, "no_category"),
        ({"category": "gadgets"}, {}, "unknown_category:gadgets"),
    ],
)
async def test_missing_inputs_fail_open_without_guessing(
    before_overrides: dict[str, Any], returned_overrides: dict[str, Any], reason: str
) -> None:
    from returns_manager.batch.runner import _NoDbQuota

    res = await _process(_before(**before_overrides), _returned(**returned_overrides), _NoDbQuota(rpm=60))
    _assert_fail_open(res, reason)


def test_batch_code_has_no_answer_key_or_clue_inference() -> None:
    """Belt and braces for the behavioural tests above: the answer-key CSV, the free-text
    `scenario` column and the former filename heuristic are not referenced in the batch code."""
    src = Path(__file__).resolve().parents[2] / "src" / "returns_manager"
    text = "\n".join(p.read_text(encoding="utf-8") for p in (src / "batch").glob("*.py"))
    text += (src / "api" / "routes" / "batch.py").read_text(encoding="utf-8")
    for needle in ("returns_output_30", "manual_test_images", "scenario", "_extract_filename", "similarity"):
        assert needle not in text, needle


# ── auto-approve never overrides the engine (A5/A2) ───────────────────────────────
# One implementation (batch/auto_approve.py); the UI only reads its flag. It can only let an
# engine route stand when the engine asked for neither review nor sign-off.


def _confident(j: Any, value: float = 0.95) -> Any:
    from returns_manager.llm.schemas import JudgmentV1

    raw = j.model_dump(mode="json")

    def bump(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "confidence" and isinstance(v, (int, float)):
                    o[k] = value
                else:
                    bump(v)
        elif isinstance(o, list):
            for x in o:
                bump(x)

    bump(raw)
    return JudgmentV1.model_validate(raw)


def _sealed_new(ctx: Any, confidence: float = 0.95) -> Any:
    from returns_manager.llm.schemas import JudgmentV1

    raw = b.grade(b.judgment(ctx), "new", ctx).model_dump(mode="json")
    raw["condition"]["packaging_state"] = "factory_sealed_intact"
    return _confident(JudgmentV1.model_validate(raw), confidence)


def test_auto_approve_marks_a_clean_engine_restock_without_changing_it() -> None:
    from returns_manager.batch import auto_approve

    ctx = b.context(b.headphones_card())
    result = b.run(ctx, _sealed_new(ctx))
    before = (
        result.decision.recommended_disposition,
        result.decision.rule_id,
        result.condition.amazon_condition,
    )
    approval = auto_approve.evaluate(result, id_mismatch=False, id_not_checked=False, threshold_bp=8500)
    assert approval.approved is True
    assert approval.blocked_by == ()
    assert approval.min_confidence_bp == 9500
    # Nothing about the engine's decision moved.
    assert (
        result.decision.recommended_disposition,
        result.decision.rule_id,
        result.condition.amazon_condition,
    ) == before
    assert before[:2] == ("restock", "R12")
    assert (
        _operator_disposition(result.decision.recommended_disposition, auto_approved=approval.approved)
        == "restock"
    )


def test_auto_approve_threshold_comes_from_config_and_blocks_low_confidence() -> None:
    from returns_manager.batch import auto_approve
    from returns_manager.config import Settings

    assert Settings.model_fields["rm_batch_auto_approve_min_confidence_bp"].default == 8500
    ctx = b.context(b.headphones_card())
    result = b.run(ctx, _sealed_new(ctx, confidence=0.84))
    approval = auto_approve.evaluate(result, id_mismatch=False, id_not_checked=False, threshold_bp=8500)
    assert approval.approved is False
    assert "confidence_below_threshold" in approval.blocked_by
    assert (
        _operator_disposition(result.decision.recommended_disposition, auto_approved=approval.approved)
        == "pending_review"
    )


def test_auto_approve_never_skips_s02_high_value_signoff() -> None:
    from returns_manager.batch import auto_approve

    ctx = b.context(b.headphones_card(price_minor=900000))
    j = b.component(
        ctx, b.judgment(ctx), "usb_cable", status="missing", visibility="observed_absent_in_clear_view"
    )
    result = b.run(ctx, _confident(b.grade(j, "used_good", ctx)))
    assert result.decision.requires_signoff is True
    approval = auto_approve.evaluate(result, id_mismatch=False, id_not_checked=False, threshold_bp=0)
    assert approval.approved is False
    assert "requires_signoff" in approval.blocked_by


def test_auto_approve_never_skips_s01_dispose_signoff() -> None:
    from returns_manager.batch import auto_approve

    ctx = b.context(b.headphones_card())
    result = b.run(ctx, _sealed_new(ctx))
    forced = type(result.decision)(
        **{**result.decision.__dict__, "recommended_disposition": "dispose", "requires_signoff": True}
    )
    approval = auto_approve.evaluate(
        type(result)(**{**result.__dict__, "decision": forced}),
        id_mismatch=False,
        id_not_checked=False,
        threshold_bp=0,
    )
    assert approval.approved is False
    assert "requires_signoff" in approval.blocked_by


def test_auto_approve_blocked_by_id_mismatch_and_by_null_recommendation() -> None:
    from returns_manager.batch import auto_approve
    from returns_manager.llm.schemas import JudgmentV1

    ctx = b.context(b.headphones_card())
    clean = b.run(ctx, _sealed_new(ctx))
    assert (
        "sold_vs_returned_id_mismatch"
        in auto_approve.evaluate(clean, id_mismatch=True, id_not_checked=False, threshold_bp=0).blocked_by
    )

    raw = _sealed_new(ctx).model_dump(mode="json")
    raw["identity"]["identity_match"] = "no"
    for fc in raw["identity"]["feature_checks"]:
        fc["result"] = "mismatch"
    wrong = b.run(ctx, JudgmentV1.model_validate(raw))
    approval = auto_approve.evaluate(wrong, id_mismatch=False, id_not_checked=False, threshold_bp=0)
    assert approval.approved is False
    assert "requires_signoff" in approval.blocked_by  # R03 dispose (S01)
    assert "image_identity_not_matched" in approval.blocked_by


def test_auto_approve_blocks_damage_and_uncertain_visual_identity() -> None:
    from returns_manager.batch import auto_approve
    from returns_manager.llm.schemas import JudgmentV1

    ctx = b.context(b.headphones_card())
    raw = _sealed_new(ctx).model_dump(mode="json")
    raw["model_observed_state"] = "damaged"
    damaged = b.run(ctx, JudgmentV1.model_validate(raw))
    damage_result = auto_approve.evaluate(damaged, id_mismatch=False, id_not_checked=False, threshold_bp=0)
    assert damage_result.approved is False
    assert "damage_observed" in damage_result.blocked_by

    raw["model_observed_state"] = "opened_unused"
    raw["identity"]["identity_match"] = "uncertain"
    uncertain_identity = b.run(ctx, JudgmentV1.model_validate(raw))
    identity_result = auto_approve.evaluate(
        uncertain_identity, id_mismatch=False, id_not_checked=False, threshold_bp=0
    )
    assert identity_result.approved is False
    assert "image_identity_not_matched" in identity_result.blocked_by


def test_row_detail_keeps_the_engine_rule_id_and_route() -> None:
    """A2: the detail's decision is the engine's, never a heuristic rewrite (e.g. R06_AUTO_RESTOCK)."""
    ctx = b.context(b.headphones_card())
    j = b.component(
        ctx, b.judgment(ctx), "usb_cable", status="missing", visibility="observed_absent_in_clear_view"
    )
    result = b.run(ctx, b.grade(j, "used_good", ctx))
    detail = _build_row_detail(session_judgment=j, result=result, row=_returned(), before=_before())
    assert detail["decision"]["rule_id"] == result.decision.rule_id == "R09"
    assert detail["decision"]["recommended_disposition"] == "refurbish"
    assert "similarity" not in detail


def _signoff_job(svc: BatchJobsService, created_by: str) -> None:
    _done_job(svc, "org_demo_alpha", "job-1")
    svc._jobs["job-1"].created_by = created_by
    (svc._job_dir("org_demo_alpha", "job-1") / "rows_detail.json").write_text(
        json.dumps({"RTN-1": {"decision": {"recommended_disposition": "dispose", "requires_signoff": True}}})
    )


def test_uploader_cannot_sign_off_a_row_that_requires_signoff(tmp_path: Path) -> None:
    from returns_manager.security.roles import Forbidden

    svc = _service(tmp_path)
    _signoff_job(svc, created_by="user:op_alex")
    assert svc.row_requires_signoff("org_demo_alpha", "job-1", "RTN-1") is True
    for action in ("accept", "override"):
        with pytest.raises(Forbidden):
            svc.record_decision(
                "org_demo_alpha",
                "job-1",
                "RTN-1",
                action=action,  # type: ignore[arg-type]
                new_disposition="dispose",
                reason="ok",
                actor="user:op_alex",
            )
    # A review request by the uploader is fine; a different person may sign off.
    assert svc.record_decision(
        "org_demo_alpha",
        "job-1",
        "RTN-1",
        action="review_request",
        new_disposition=None,
        reason="look",
        actor="user:op_alex",
    )
    assert svc.record_decision(
        "org_demo_alpha",
        "job-1",
        "RTN-1",
        action="accept",
        new_disposition=None,
        reason="ok",
        actor="user:rev_priya",
    )


def test_ui_reads_the_backend_auto_approve_flag_and_has_no_copy_of_the_rule() -> None:
    ui = Path(__file__).resolve().parents[3] / "ui" / "src"
    store = (ui / "lib" / "store.tsx").read_text(encoding="utf-8")
    assert "row.auto_approved === 'true'" in store
    assert not (ui / "lib" / "similarity.ts").exists()
    everything = "\n".join(p.read_text(encoding="utf-8") for p in ui.rglob("*.ts*"))
    for needle in ("computeRowSimilarity", ">= 85", "confidence >= "):
        assert needle not in everything, needle


def test_accepting_a_signoff_row_over_http_needs_the_signoff_permission(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from returns_manager.api import problems
    from returns_manager.api.deps import Services, principal
    from returns_manager.api.routes.batch import router
    from returns_manager.security.roles import Principal, Scope

    svc = _service(tmp_path)
    _signoff_job(svc, created_by="user:op_alex")
    app = FastAPI()
    problems.install(app)
    app.include_router(router)
    app.state.services = Services(
        settings=Settings.model_construct(), db=None, jwt=None, storage=None, batch_jobs=svc
    )  # type: ignore[arg-type]
    url = "/api/v1/batch/jobs/job-1/rows/RTN-1/decision"
    body = {"action": "accept", "reason": "ok"}

    app.dependency_overrides[principal] = lambda: Principal(
        kind="api_key", org_id="org_demo_alpha", actor_id="k1", scopes=frozenset({Scope.RETURNS_WRITE})
    )
    assert TestClient(app).post(url, json=body).status_code == 403

    app.dependency_overrides[principal] = lambda: Principal(
        kind="api_key",
        org_id="org_demo_alpha",
        actor_id="k2",
        scopes=frozenset({Scope.RETURNS_WRITE, Scope.REVIEW_WRITE}),
    )
    assert TestClient(app).post(url, json=body).status_code == 201


# ── no invented input data (Stage 2 item 1) ────────────────────────────────────────
# A missing required column or a blank record_id/unit_id is a 400 naming the file, line and
# column. Any other blank stays blank. A blank ID on either side is "not checked", never
# "matched", and it blocks auto-approve.

_COMBINED_HEADER = (
    "unit_id,category,parts_list,identity_match,sold_record_id,sold_org_id,sold_order_id,sold_sku,"
    "sold_asin,sold_time,sold_photo_url,returned_record_id,returned_org_id,returned_order_id,"
    "returned_sku,returned_asin,returned_time,returned_photo_url"
)
_COMBINED_ROW = (
    "UNIT-1,electronics,handset,yes,PCK-1,org_demo_alpha,ORD-1,SKU-A,ASIN-A,2026-08-01T09:00:00Z,"
    "https://example.com/ref.jpg,RTN-1,org_demo_alpha,ORD-1,SKU-A,ASIN-A,2026-09-01T10:00:00Z,"
    "https://example.com/a.jpg"
)
_BEFORE_HEADER = (
    "record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,identity_match,parts_list,time,photo_ref"
)
_RETURNED_HEADER = "record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,returned_photo_ref,time"


def _upload_client(tmp_path: Path) -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from returns_manager.api import problems
    from returns_manager.api.deps import Services, principal
    from returns_manager.api.routes.batch import router
    from returns_manager.security.roles import Principal, Scope

    app = FastAPI()
    problems.install(app)
    app.include_router(router)
    app.state.services = Services(
        settings=Settings.model_construct(), db=None, jwt=None, storage=None, batch_jobs=_service(tmp_path)
    )  # type: ignore[arg-type]
    app.dependency_overrides[principal] = lambda: Principal(
        kind="api_key", org_id="org_demo_alpha", actor_id="k1", scopes=frozenset({Scope.RETURNS_WRITE})
    )
    return TestClient(app)


def _post(client: Any, files: dict[str, tuple[str, str]]) -> Any:
    return client.post(
        "/api/v1/batch/jobs",
        data={"confirm_spend": "true"},
        files={k: (name, body.encode("utf-8"), "text/csv") for k, (name, body) in files.items()},
    )


def test_upload_missing_required_column_is_400_naming_file_and_column(tmp_path: Path) -> None:
    client = _upload_client(tmp_path)
    before = _BEFORE_HEADER.replace(",ordered_sku", "") + "\nPCK-1,UNIT-1,org,ORD-1,ASIN-A,yes,x,t,u\n"
    returned = _RETURNED_HEADER + "\nRTN-1,UNIT-1,org,ORD-1,SKU-A,ASIN-A,https://e/a.jpg,t\n"
    resp = _post(client, {"before": ("my_before.csv", before), "returned": ("my_returned.csv", returned)})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "my_before.csv" in detail
    assert "ordered_sku" in detail


def test_upload_blank_required_value_is_400_naming_file_line_and_column(tmp_path: Path) -> None:
    client = _upload_client(tmp_path)
    before = _BEFORE_HEADER + "\nPCK-1,UNIT-1,org,ORD-1,SKU-A,ASIN-A,yes,x,t,u\n"
    returned = (
        _RETURNED_HEADER
        + "\nRTN-1,UNIT-1,org,ORD-1,SKU-A,ASIN-A,https://e/a.jpg,t"
        + "\nRTN-2,,org,ORD-2,SKU-A,ASIN-A,https://e/b.jpg,t\n"
    )
    resp = _post(client, {"before": ("b.csv", before), "returned": ("r.csv", returned)})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "r.csv, line 3, column 'unit_id': required value is blank"


def test_combined_upload_missing_required_column_is_400(tmp_path: Path) -> None:
    client = _upload_client(tmp_path)
    header = _COMBINED_HEADER.replace("unit_id,", "", 1)
    row = _COMBINED_ROW.split(",", 1)[1]
    resp = _post(client, {"file": ("combined.csv", f"{header}\n{row}\n")})
    assert resp.status_code == 400
    assert "combined.csv" in resp.json()["detail"]
    assert "unit_id" in resp.json()["detail"]


def test_combined_upload_blank_record_id_is_400_naming_line_and_column(tmp_path: Path) -> None:
    client = _upload_client(tmp_path)
    blank_returned_id = _COMBINED_ROW.replace("RTN-1", "")
    body = f"{_COMBINED_HEADER}\n{_COMBINED_ROW}\n{blank_returned_id}\n"
    resp = _post(client, {"file": ("c.csv", body)})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "c.csv, line 3, column 'returned_record_id': required value is blank"


def test_combined_upload_without_sold_and_returned_columns_is_rejected(tmp_path: Path) -> None:
    """Formerly the same file was used as both the before and the returned file, so every row was
    compared with itself and reported "matched"."""
    client = _upload_client(tmp_path)
    body = _RETURNED_HEADER + "\nRTN-1,UNIT-1,org,ORD-1,SKU-A,ASIN-A,https://e/a.jpg,t\n"
    resp = _post(client, {"file": ("one.csv", body)})
    assert resp.status_code == 400
    assert "sold_* and returned_*" in resp.json()["detail"]


def test_split_invents_nothing_for_blank_optional_fields() -> None:
    from returns_manager.api.routes.batch import _split_combined_csv
    from returns_manager.batch.io_csv import parse_before_csv, parse_returned_csv

    fields = _COMBINED_HEADER.split(",")
    values = dict(zip(fields, _COMBINED_ROW.split(","), strict=True))
    for blank in (
        "sold_order_id",
        "returned_sku",
        "returned_asin",
        "identity_match",
        "sold_time",
        "sold_org_id",
    ):
        values[blank] = ""
    body = _COMBINED_HEADER + "\n" + ",".join(values[f] for f in fields) + "\n"
    b_bytes, r_bytes = _split_combined_csv(body.encode("utf-8"), "c.csv")

    before = parse_before_csv(b_bytes.decode("utf-8"), "b")["UNIT-1"]
    returned = parse_returned_csv(r_bytes.decode("utf-8"), "r")[0]
    assert (before.order_id, before.identity_match, before.time, before.org_id) == ("", "", "", "")
    assert (returned.ordered_sku, returned.ordered_asin) == ("", "")
    # The other side's value is never copied across.
    assert returned.order_id == "ORD-1"
    assert before.ordered_sku == "SKU-A"
    text = (b_bytes + r_bytes).decode("utf-8")
    for invented in ("SKU-DEFAULT", "B0DEFAULT", "REC-", "UNIT-2", "2026-08-01T00:00:00Z", "uncertain"):
        assert invented not in text


def test_split_reads_each_side_only_from_its_own_prefixed_columns() -> None:
    """A shared unprefixed ID column is not copied to both sides: that would compare a value with
    itself and report a false "matched"."""
    from returns_manager.api.routes.batch import _split_combined_csv
    from returns_manager.batch.io_csv import parse_before_csv, parse_returned_csv

    body = (
        "unit_id,order_id,ordered_sku,sold_record_id,returned_record_id,sold_photo_url,returned_photo_url\n"
        "UNIT-1,ORD-1,SKU-A,PCK-1,RTN-1,https://e/ref.jpg,https://e/a.jpg\n"
    )
    b_bytes, r_bytes = _split_combined_csv(body.encode("utf-8"), "c.csv")
    before = parse_before_csv(b_bytes.decode("utf-8"), "b")["UNIT-1"]
    returned = parse_returned_csv(r_bytes.decode("utf-8"), "r")[0]
    assert (before.order_id, returned.order_id, before.ordered_sku, returned.ordered_sku) == ("", "", "", "")
    assert check_id_match(before, returned).startswith("not checked:")


@pytest.mark.parametrize("field", ["org_id", "order_id", "ordered_sku", "ordered_asin"])
@pytest.mark.parametrize("side", ["sold", "returned", "both"])
def test_blank_id_is_never_matched(field: str, side: str) -> None:
    before = _before(**{field: ""}) if side in ("sold", "both") else _before()
    returned = _returned(**{field: ""}) if side in ("returned", "both") else _returned()
    result = check_id_match(before, returned)
    assert result != "matched"
    assert result.startswith(f"not checked: {field} missing")
    assert not _id_mismatch(before, result)


def test_blank_id_alongside_a_real_mismatch_reports_both() -> None:
    result = check_id_match(_before(order_id=""), _returned(ordered_sku="SKU-B"))
    assert result.startswith("NOT MATCHED: ordered_sku")
    assert "not checked: order_id missing (sold)" in result
    assert _id_mismatch(_before(), result)


def test_uncertain_row_with_blank_ids_is_not_checked() -> None:
    out = _uncertain_row(_returned(order_id="", ordered_asin=""), _before(), "no_return_photo")
    assert out["sold_vs_returned_id_check"] == (
        "not checked: order_id missing (returned); ordered_asin missing (returned)"
    )


def test_blank_id_blocks_auto_approve() -> None:
    from returns_manager.batch import auto_approve
    from returns_manager.batch.runner import _id_not_checked

    ctx = b.context(b.headphones_card())
    clean = b.run(ctx, _sealed_new(ctx))
    id_check = check_id_match(_before(order_id=""), _returned())
    approval = auto_approve.evaluate(
        clean,
        id_mismatch=_id_mismatch(_before(), id_check),
        id_not_checked=_id_not_checked(id_check),
        threshold_bp=0,
    )
    assert approval.approved is False
    assert approval.blocked_by == ("sold_vs_returned_id_not_checked",)


def test_ui_shows_pass_only_for_a_real_match() -> None:
    """The UI labels the ID check from the backend string; "not checked" must never render PASS."""
    ui = Path(__file__).resolve().parents[3] / "ui" / "src"
    for screen in ("Inspection.tsx", "Dashboard.tsx", "Reviews.tsx"):
        text = (ui / "screens" / screen).read_text(encoding="utf-8")
        assert "? 'FAIL' : 'PASS'" not in text, screen
    derive = (ui / "lib" / "derive.ts").read_text(encoding="utf-8")
    assert "check === 'matched'" in derive


# ── progress writer surfaces serialization bugs (Stage 2 item 2) ───────────────────
# Only OSError (a disk write) is tolerated mid-run. A TypeError from json.dumps is a bug in our
# own row detail: the job fails with that error instead of logging it and carrying on.


def _progress_job(svc: BatchJobsService, tmp_path: Path) -> BatchJob:
    job = BatchJob(
        job_id="job-p",
        org_id="org_demo_alpha",
        status="queued",
        created_at=time.time(),
        before_filename="before.csv",
        returned_filename="returned.csv",
    )
    svc._jobs[job.job_id] = job
    svc._job_dir(job.org_id, job.job_id).mkdir(parents=True, exist_ok=True)
    return job


def _fake_run_batch(detail: Any) -> Any:
    from returns_manager.batch.runner import BatchSummary, _report_progress

    async def _run(**kwargs: Any) -> Any:
        summary = BatchSummary(total_rows=1, processed=1)
        rows = [{"record_id": "RTN-1"}]
        _report_progress(kwargs["on_progress"], rows[0], detail, summary, rows, {"RTN-1": detail})
        # The final details are serializable, so only the progress write sees the bad detail: the
        # old code logged that TypeError and finished the job as "done".
        return rows, {}, summary

    return _run


async def test_non_serializable_detail_fails_the_job_loudly(tmp_path: Path, monkeypatch: Any) -> None:
    from returns_manager.batch import jobs_service

    svc = _service(tmp_path)
    job = _progress_job(svc, tmp_path)
    monkeypatch.setattr(jobs_service, "run_batch", _fake_run_batch({"when": object()}))
    await svc._run(job, None, 1)
    assert job.status == "failed"
    assert job.error is not None
    assert job.error.startswith("TypeError:")
    assert "not JSON serializable" in job.error


def test_report_progress_does_not_swallow_a_type_error() -> None:
    from returns_manager.batch.runner import _report_progress

    def _bad(*args: Any) -> None:
        raise TypeError("Object of type object is not JSON serializable")

    with pytest.raises(TypeError):
        _report_progress(_bad, {})


async def test_progress_disk_write_failure_is_tolerated(tmp_path: Path, monkeypatch: Any) -> None:
    from returns_manager.batch import io_csv, jobs_service

    svc = _service(tmp_path)
    job = _progress_job(svc, tmp_path)
    monkeypatch.setattr(jobs_service, "run_batch", _fake_run_batch({"ok": 1}))
    real_write = io_csv.write_output_csv
    calls = {"n": 0}

    def _flaky(path: Path, rows: list[dict[str, str]]) -> None:
        calls["n"] += 1
        if calls["n"] == 1:  # the mid-run progress write fails; the final write succeeds
            raise OSError("disk full")
        real_write(path, rows)

    monkeypatch.setattr(io_csv, "write_output_csv", _flaky)
    await svc._run(job, None, 1)
    assert job.status == "done"
    assert calls["n"] == 2


# ── honest list price (Stage 2 item 3, audit C3) ───────────────────────────────────
# A before-row may carry list_price (rupees) or list_price_minor (paise). Without one, the
# configured default is used and the row says value_source=synthetic_default, in the output
# and in the row detail, so a synthetic price is never presented as real.


def _before_csv(extra_header: str = "", extra_value: str = "") -> str:
    return (
        _BEFORE_HEADER
        + extra_header
        + "\nPCK-1,UNIT-1,org,ORD-1,SKU-A,ASIN-A,yes,x,t,https://e/ref.jpg"
        + extra_value
        + "\n"
    )


@pytest.mark.parametrize(
    ("header", "value", "minor"),
    [
        (",list_price", ",1299.50", 129950),
        (",list_price", ",1299", 129900),
        (",list_price_minor", ",129950", 129950),
        (",list_price,list_price_minor", ",1299.50,129950", 129950),
        ("", "", None),
        (",list_price", ",", None),
    ],
)
def test_list_price_parsed_from_rupees_or_paise(header: str, value: str, minor: int | None) -> None:
    from returns_manager.batch.io_csv import parse_before_csv

    assert parse_before_csv(_before_csv(header, value), "b.csv")["UNIT-1"].list_price_minor == minor


@pytest.mark.parametrize(
    ("header", "value", "column"),
    [
        (",list_price", ",12.345", "list_price"),
        (",list_price", ",-5", "list_price"),
        (",list_price", ",abc", "list_price"),
        (",list_price_minor", ",12.5", "list_price_minor"),
        (",list_price,list_price_minor", ",1299.50,129900", "list_price_minor"),
    ],
)
def test_bad_list_price_names_file_line_and_column(header: str, value: str, column: str) -> None:
    from returns_manager.batch.io_csv import CsvInputError, parse_before_csv

    with pytest.raises(CsvInputError) as err:
        parse_before_csv(_before_csv(header, value), "b.csv")
    assert (err.value.filename, err.value.line, err.value.column) == ("b.csv", 2, column)


def test_combined_upload_bad_list_price_is_400(tmp_path: Path) -> None:
    client = _upload_client(tmp_path)
    body = f"{_COMBINED_HEADER},list_price\n{_COMBINED_ROW},lots\n"
    resp = _post(client, {"file": ("c.csv", body)})
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("c.csv, line 2, column 'list_price':")


def test_split_carries_the_list_price_through() -> None:
    from returns_manager.api.routes.batch import _split_combined_csv
    from returns_manager.batch.io_csv import parse_before_csv

    body = f"{_COMBINED_HEADER},list_price\n{_COMBINED_ROW},2499.00\n"
    b_bytes, _ = _split_combined_csv(body.encode("utf-8"), "c.csv")
    assert parse_before_csv(b_bytes.decode("utf-8"), "b")["UNIT-1"].list_price_minor == 249900


def test_value_record_csv_price_is_marked_as_from_the_csv() -> None:
    from returns_manager.batch.runner import value_record

    ctx = b.context(b.headphones_card())
    result = b.run(ctx, _sealed_new(ctx))
    rec = value_record(_before(list_price_minor=450000), 999900, result.decision)
    assert rec["list_price_minor"] == 450000
    assert rec["value_source"] == "csv_list_price"
    # Recovery rates and refurbish cost are still placeholders, and say so.
    assert rec["recovery_rates_source"] == rec["refurbish_cost_source"] == "synthetic_default"


def test_value_record_without_csv_price_is_synthetic_default() -> None:
    from returns_manager.batch.runner import value_record

    ctx = b.context(b.headphones_card())
    result = b.run(ctx, _sealed_new(ctx))
    rec = value_record(_before(), 999900, result.decision)
    assert rec["list_price_minor"] == 999900
    assert rec["value_source"] == "synthetic_default"


def test_value_record_names_the_value_driven_outcomes() -> None:
    from returns_manager.batch.runner import value_record

    ctx = b.context(b.headphones_card())
    j = b.component(
        ctx, b.judgment(ctx), "usb_cable", status="missing", visibility="observed_absent_in_clear_view"
    )
    r09 = b.run(ctx, b.grade(j, "used_good", ctx))
    assert value_record(_before(), 999900, r09.decision)["value_driven_outcomes"] == ["R09"]

    ctx_hv = b.context(b.headphones_card(price_minor=900000))
    j_hv = b.component(
        ctx_hv, b.judgment(ctx_hv), "usb_cable", status="missing", visibility="observed_absent_in_clear_view"
    )
    s02 = b.run(ctx_hv, _confident(b.grade(j_hv, "used_good", ctx_hv)))
    assert "S02_high_value" in value_record(_before(), 900000, s02.decision)["value_driven_outcomes"]

    clean = b.run(ctx, _sealed_new(ctx))
    assert value_record(_before(), 999900, clean.decision)["value_driven_outcomes"] == []


def test_output_row_records_value_source_on_both_paths() -> None:
    assert _uncertain_row(_returned(), _before(), "x")["value_source"] == ""
    assert _uncertain_row(_returned(), _before(list_price_minor=12300), "x")["value_source"] == ""
    assert _uncertain_row(_returned(), None, "x")["value_source"] == ""


async def test_the_csv_price_reaches_the_card_and_the_default_is_used_otherwise(monkeypatch: Any) -> None:
    """process_returned_row prices the synthesized card from the CSV when given, else the default."""
    from returns_manager.batch import runner

    seen: list[int] = []

    def _capture(**kwargs: Any) -> Any:
        seen.append(kwargs["list_price_minor"])
        raise _Stop

    class _Stop(Exception):
        pass

    monkeypatch.setattr(runner, "build_card", _capture)
    for before, expected in ((_before(list_price_minor=450000), 450000), (_before(), 999900)):
        with pytest.raises(_Stop):
            await runner.process_returned_row(
                _returned(),
                {"UNIT-1": before},
                settings=Settings.model_construct(),
                client=None,  # type: ignore[arg-type]
                http_client=None,  # type: ignore[arg-type]
                quota=runner._NoDbQuota(1),
                default_category=None,
                list_price_minor=999900,
            )
        assert seen[-1] == expected


def test_ui_labels_an_assumed_price_from_the_backend_record_only() -> None:
    ui = Path(__file__).resolve().parents[3] / "ui" / "src"
    inspection = (ui / "screens" / "Inspection.tsx").read_text(encoding="utf-8")
    assert "price assumed (synthetic)" in inspection
    assert "detail?.value?.value_source === 'synthetic_default'" in inspection
    assert "value_driven_outcomes.includes('S02_high_value')" in inspection
    # No client-side copy of the value rules.
    for rule in ("'R09'", "'R10'", "high_value_threshold"):
        assert rule not in inspection


# ── Inspection comparison record (Stage 2 item 4) ──────────────────────────────────
# The panel reads only backend fields: the card's features joined with the model's own
# check for each, plain counts of the critical ones, and alias -> URL for every photo.


def test_photo_aliases_follow_the_fetched_photos_not_the_csv_order() -> None:
    from returns_manager.batch.runner import photo_aliases

    # b.jpg failed to fetch, so the model saw a.jpg as P1 and c.jpg as P2.
    aliases = photo_aliases("https://e/ref.jpg", ["https://e/a.jpg", "https://e/c.jpg"])
    assert aliases == {"ref_before": "https://e/ref.jpg", "P1": "https://e/a.jpg", "P2": "https://e/c.jpg"}


def test_comparison_record_counts_critical_features_from_the_model_checks() -> None:
    from returns_manager.batch.runner import comparison_record

    ctx = b.context(b.headphones_card())
    j = b.judgment(ctx)
    critical = [f for f in ctx.card.distinguishing_features if f.importance == "critical"]
    rec = comparison_record(ctx.card, j, {"ref_before": "r", "P1": "a"}, ["https://e/b.jpg"])
    by_id = {f["feature_id"]: f for f in rec["features"]}
    assert set(by_id) == {f.id for f in ctx.card.distinguishing_features}
    for fc in j.identity.feature_checks:
        assert by_id[fc.feature_id]["result"] == fc.result
        assert by_id[fc.feature_id]["photo"] == fc.photo
    counts = rec["critical_features"]
    assert counts["total"] == len(critical)
    assert counts["matched"] == sum(1 for f in critical if by_id[f.id]["result"] == "match")
    assert (
        counts["matched"] + counts["mismatched"] + counts["not_visible"] + counts["not_reported"]
        == counts["total"]
    )
    assert rec["unfetched_photo_refs"] == ["https://e/b.jpg"]
    json.dumps(rec)


def test_comparison_record_reports_mismatch_and_unreported_features() -> None:
    from returns_manager.batch.runner import comparison_record

    ctx = b.context(b.headphones_card())
    raw = b.judgment(ctx).model_dump(mode="json")
    checks = raw["identity"]["feature_checks"]
    assert len(checks) >= 2
    checks[0]["result"] = "mismatch"
    dropped = checks.pop()
    j = type(b.judgment(ctx)).model_validate(raw)
    rec = comparison_record(ctx.card, j, {}, [])
    by_id = {f["feature_id"]: f for f in rec["features"]}
    assert by_id[checks[0]["feature_id"]]["result"] == "mismatch"
    assert by_id[dropped["feature_id"]]["result"] == "not_reported"
    assert by_id[dropped["feature_id"]]["photo"] is None
    assert rec["critical_features"]["mismatched"] >= 1
    assert rec["critical_features"]["not_reported"] >= 1
    assert "similarity" not in json.dumps(rec)


def test_ui_comparison_panel_reads_backend_fields_and_shows_no_score() -> None:
    ui = Path(__file__).resolve().parents[3] / "ui" / "src"
    panel = (ui / "screens" / "InspectionComparison.tsx").read_text(encoding="utf-8")
    assert "detail.comparison" in panel
    assert "Not inspected: " in panel
    assert "model-reported, not calibrated" in panel
    assert "critical features matched" in panel
    lowered = panel.lower()
    assert "similarity" not in lowered
    # Counts come from the backend record; the panel never tallies results itself.
    assert re.search(r"\.filter\([^)]*\)\.length", panel) is None
    assert ".reduce(" not in panel
    assert "counts.matched" in panel
    assert "InspectionComparison" in (ui / "screens" / "Inspection.tsx").read_text(encoding="utf-8")


# ── Run request cap (Stage 3, before the live smoke run) ────────────────────────────
# `--max-requests` caps real requests, not rows: every session round trip and retry takes one
# from the quota right before it is sent, and "live model requests used" is that count.


def _write_csvs(tmp_path: Path, n: int) -> tuple[Path, Path]:
    before = tmp_path / "before.csv"
    returned = tmp_path / "returned.csv"
    before.write_text(
        _BEFORE_HEADER
        + "".join(f"\nPCK-{i},UNIT-{i},org,ORD-{i},SKU-A,ASIN-A,yes,x,t,https://e/ref.jpg" for i in range(n)),
        encoding="utf-8",
    )
    returned.write_text(
        "record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,returned_photo_ref,time"
        + "".join(f"\nRTN-{i},UNIT-{i},org,ORD-{i},SKU-A,ASIN-A,https://e/p{i}.jpg,t" for i in range(n)),
        encoding="utf-8",
    )
    return before, returned


async def test_max_requests_caps_real_requests_not_rows(tmp_path: Path, monkeypatch: Any) -> None:
    """Each row's session wants 2 requests (a tool round trip). With a cap of 3: row 0 sends 2,
    row 1 sends 1 and is refused the 2nd, row 2 sends none. The old code counted one request per
    row (reporting 2) and let row 1 send its 2nd request (4 sent)."""
    from returns_manager.batch import runner
    from returns_manager.llm.loop import SessionFailed, SessionTrace

    attempted: list[int] = []  # every take() that got past the cap, i.e. a request that is sent

    async def _two_request_row(row: Any, before_by_unit: Any, *, quota: Any, **kwargs: Any) -> Any:
        before = before_by_unit[row.unit_id]
        trace = SessionTrace(model="m", output_mode="x")
        try:
            async with quota.reserve("m", "judgment", 2) as reservation:
                for _ in range(2):
                    await reservation.take()
                    attempted.append(1)
                    trace.requests_sent += 1
        except runner.RequestCapReached as exc:
            failed = SessionFailed(exc, trace)
            return runner._fail_open(
                row, before, "max_requests_reached", attempted_model_call=failed.trace.requests_sent > 0
            )
        return runner._fail_open(row, before, "stub_done", attempted_model_call=True)

    monkeypatch.setattr(runner, "process_returned_row", _two_request_row)
    before, returned = _write_csvs(tmp_path, 3)
    rows, _details, summary = await runner.run_batch(
        before_path=before,
        returned_path=returned,
        settings=Settings.model_construct(rm_rpm_limit_judgment=6000),
        client=None,  # type: ignore[arg-type]
        max_requests=3,
    )
    assert len(attempted) == 3
    assert summary.live_requests == 3
    reasons = [r["failure_reason"] for r in rows]
    assert reasons == ["stub_done", "max_requests_reached", "max_requests_reached"]


async def test_request_cap_refuses_before_sending_and_counts_each_take() -> None:
    from returns_manager.batch.runner import RequestCapReached, _NoDbQuota

    quota = _NoDbQuota(rpm=6000, max_requests=2)
    async with quota.reserve("m", "judgment", 2) as reservation:
        await reservation.take()
        await reservation.take()
        with pytest.raises(RequestCapReached):
            await reservation.take()
    assert quota.requests_sent == 2
    assert quota.cap_reached is True
    with pytest.raises(RequestCapReached):
        async with quota.reserve("m", "judgment", 1):
            pass
    uncapped = _NoDbQuota(rpm=6000)
    async with uncapped.reserve("m", "judgment", 1) as reservation:
        await reservation.take()
    assert uncapped.requests_sent == 1
    assert uncapped.cap_reached is False


@pytest.mark.db
async def test_batch_records_real_requests_in_the_quota_ledger_when_db_is_available(
    db: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    """The DB-backed batch runner must reserve its live requests through the real ledger, not the
    in-memory standalone stub; the unused reservation is released, leaving the ledger with 1 used."""
    from returns_manager.batch import runner

    before, returned = _write_csvs(tmp_path, 1)
    model_id = f"batch-db-ledger-test-model-{__import__('uuid').uuid4().hex}"

    async def _fake_row(row: Any, before_by_unit: Any, *, quota: Any, **kwargs: Any) -> Any:
        before = before_by_unit[row.unit_id]
        async with quota.reserve(model_id, "judgment", 2) as reservation:
            await reservation.take()
        return runner._fail_open(row, before, "stub_done", attempted_model_call=True)

    monkeypatch.setattr(runner, "process_returned_row", _fake_row)
    await runner.run_batch(
        before_path=before,
        returned_path=returned,
        settings=Settings.model_construct(rm_rpm_limit_judgment=6000),
        client=None,  # type: ignore[arg-type]
        db=db,
    )
    async with db.transaction(None) as conn:
        row = await conn.execute(
            "SELECT requests_used FROM rm.model_request_ledger WHERE model_id = %s",
            (model_id,),
        )
        ledger = await row.fetchone()
    assert ledger is not None
    assert ledger["requests_used"] == 1


async def test_cap_reached_mid_session_is_not_marked_as_quota_exhausted(monkeypatch: Any) -> None:
    """A row the cap stops mid-session says max_requests_reached, and the run's daily-quota flag
    stays off: the provider never said the quota was used up."""
    from returns_manager.batch import runner
    from returns_manager.llm.loop import SessionFailed, SessionTrace

    async def _cap_mid_session(*args: Any, **kwargs: Any) -> Any:
        trace = SessionTrace(model="m", output_mode="x")
        trace.requests_sent = 1
        raise SessionFailed(runner.RequestCapReached("cap"), trace)

    monkeypatch.setattr(runner, "_run_judgment_with_fallback", _cap_mid_session)
    before, returned = _golden_row("RTN-WATCH-01")
    quota = runner._NoDbQuota(rpm=60, max_requests=5)
    res = await _process(before, returned, quota)
    _assert_fail_open(res, "max_requests_reached")
    assert res.attempted_model_call is True
    assert quota.is_exhausted is False
