"""Standalone batch pipeline (CSV + image-URL import, no database): pure-logic tests.

Network and live-model paths (`images.fetch_image`, `runner.run_batch`) are exercised
manually against real hosted photos, per build-log; they are not repeated here as replay
cassettes do not exist for this ad hoc path.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from returns_manager.batch.cards import VALID_CATEGORIES, build_card
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
    _operator_disposition,
    _missing_parts_field,
    _uncertain_row,
    check_id_match,
)
from returns_manager.config import Settings
from tests.unit import judgment_builders as b

# ── parts_list parsing and essential/replaceable classification ──────────────────────


def test_parse_parts_list_first_part_is_root_non_replaceable() -> None:
    parts = parse_parts_list("lamp;usb cable;manual")
    assert [p.name for p in parts] == ["lamp", "usb cable", "manual"]
    assert parts[0].essential
    assert not parts[0].replaceable
    assert all(p.essential and p.replaceable for p in parts[1:])


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
        "parts_list,parts_missing,observed_state,amazon_condition,operator_disposition,photo_refs,"
        "captured_at,sold_vs_returned_id_check,failure_reason"
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


def test_uncertain_row_without_before_record_defaults_to_uncertain_identity() -> None:
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
    assert out["identity_match"] == "uncertain"
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


def test_uncertain_row_no_sold_record_stays_pending_review() -> None:
    out = _uncertain_row(_returned(), None, "no before-record for this unit_id")
    assert out["operator_disposition"] == "pending_review"
    assert out["sold_vs_returned_id_check"] == "NOT MATCHED: no sold-record for this unit_id"


def test_operator_disposition_is_a_route_or_pending_review_only() -> None:
    assert _operator_disposition("restock", id_mismatch=False) == "restock"
    assert _operator_disposition("restock", id_mismatch=True) == "pending_review"
    assert _operator_disposition(None, id_mismatch=False) == "pending_review"
    assert _id_mismatch(_before(), "NOT MATCHED: order_id: ...") is True
    assert _id_mismatch(_before(), "matched") is False
    assert _id_mismatch(None, "NOT MATCHED: no sold-record for this unit_id") is False
    for route in DISPOSITIONS:
        assert _operator_disposition(route, id_mismatch=False) in DISPOSITIONS


def test_wrong_item_is_r03_null_recommendation_and_pending_review() -> None:
    from returns_manager.llm.schemas import JudgmentV1

    ctx = b.context(b.headphones_card())
    raw = b.judgment(ctx).model_dump(mode="json")
    raw["identity"]["identity_match"] = "no"
    for fc in raw["identity"]["feature_checks"]:
        fc["result"] = "mismatch"
    result = b.run(ctx, JudgmentV1.model_validate(raw))

    assert result.decision.rule_id == "R03"
    assert result.decision.recommended_disposition is None
    assert result.decision.no_recommendation_reason == "wrong_item_returned"
    assert result.claims.wrong_item_returned.value == "yes"
    assert _operator_disposition(result.decision.recommended_disposition, id_mismatch=False) == "pending_review"


@pytest.mark.parametrize("value", ["wrong_product", "pending_review", "RESTOCK", "return_to_vendor"])
def test_decision_request_rejects_anything_but_the_four_dispositions(value: str) -> None:
    from pydantic import ValidationError

    from returns_manager.api.routes.batch import RowDecisionRequest

    with pytest.raises(ValidationError):
        RowDecisionRequest(action="override", new_disposition=value, reason="r")  # type: ignore[arg-type]
    for route in DISPOSITIONS:
        assert RowDecisionRequest(action="override", new_disposition=route, reason="r").new_disposition == route  # type: ignore[arg-type]


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


def test_missing_parts_field_merges_missing_and_uncertain_without_duplicates() -> None:
    merged = _missing_parts_field(_FakeCompleteness("battery", "battery;battery cover"))
    assert merged == "battery;battery cover"
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
        "parts_list,parts_missing,observed_state,amazon_condition,operator_disposition,photo_refs,"
        "captured_at,sold_vs_returned_id_check,failure_reason"
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
    b_bytes, r_bytes = _split_combined_csv(content, default_org_id="org_demo_alpha")

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
        raise SessionFailed(QuotaExhaustedError("429 RESOURCE_EXHAUSTED"), SessionTrace(model="m", output_mode="x"))

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
        raise SessionFailed(SchemaError("judgment did not validate"), SessionTrace(model="m", output_mode="x"))

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
