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
    _disposition_for_id_check,
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
        "record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,identity_match,parts_list,"
        "parts_missing,observed_state,amazon_condition,operator_disposition,photo_refs,captured_at,"
        "sold_vs_returned_id_check"
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


# ── ID mismatch overrides operator_disposition to wrong_product ────────────────────
# A mismatched order/SKU/org/ASIN on the returned label outranks whatever the photo
# looked like - the fail-open row's disposition is forced to wrong_product instead of
# the usual pending_review, but only when there IS a sold record to disagree with (no
# sold record at all is a missing-data problem, not a proven mismatch).


def test_uncertain_row_marks_wrong_product_on_id_mismatch() -> None:
    row = _returned(order_id="ORD-999")
    out = _uncertain_row(row, _before(), "image_fetch_failed: timeout")
    assert out["operator_disposition"] == "wrong_product"
    assert out["sold_vs_returned_id_check"].startswith("NOT MATCHED:")


def test_uncertain_row_no_sold_record_stays_pending_review_not_wrong_product() -> None:
    out = _uncertain_row(_returned(), None, "no before-record for this unit_id")
    assert out["operator_disposition"] == "pending_review"
    assert out["sold_vs_returned_id_check"] == "NOT MATCHED: no sold-record for this unit_id"


def test_disposition_for_id_check_overrides_fallback_only_when_before_known() -> None:
    assert _disposition_for_id_check(_before(), "NOT MATCHED: order_id: ...", "restock") == "wrong_product"
    assert _disposition_for_id_check(_before(), "matched", "restock") == "restock"
    assert (
        _disposition_for_id_check(None, "NOT MATCHED: no sold-record for this unit_id", "pending_review")
        == "pending_review"
    )


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
        "record_id,unit_id,org_id,order_id,ordered_sku,ordered_asin,identity_match,parts_list,"
        "parts_missing,observed_state,amazon_condition,operator_disposition,photo_refs,captured_at,"
        "sold_vs_returned_id_check"
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


def test_similarity_confidence_auto_restocks_complete_return() -> None:
    from returns_manager.batch.similarity import compute_before_after_similarity
    from returns_manager.batch.runner import _build_synthetic_row_detail

    before = BeforeRow(
        record_id="PCK-EDGE-01",
        unit_id="UNIT-EDGE-01",
        org_id="org_demo_alpha",
        order_id="ORD-EDGE-01",
        ordered_sku="SKU-PHONE-A",
        ordered_asin="B0PHONE01",
        identity_match="uncertain",
        parts_list="handset;battery;battery cover",
        time="2026-08-02T10:15:00Z",
        photo_ref="https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d7/Samsung_Galaxy_S_2_and_its_removable_parts.jpg/1280px-Samsung_Galaxy_S_2_and_its_removable_parts.jpg",
        category="electronics",
    )
    returned = ReturnedRow(
        record_id="RTN-EDGE-01",
        unit_id="UNIT-EDGE-01",
        org_id="org_demo_alpha",
        order_id="ORD-EDGE-01",
        ordered_sku="SKU-PHONE-A",
        ordered_asin="B0PHONE01",
        time="2026-09-02T11:15:00Z",
        returned_photo_refs=(
            "https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d7/Samsung_Galaxy_S_2_and_its_removable_parts.jpg/1280px-Samsung_Galaxy_S_2_and_its_removable_parts.jpg",
        ),
    )

    sim = compute_before_after_similarity(before, returned)
    assert sim["confidence"] >= 85
    assert sim["is_auto_approved"] is True
    assert sim["recommended_disposition"] == "restock"
    assert sim["resolved_condition"] == "Used - Like New"
    assert sim["completeness_pct"] == 100
    assert sim["visual_match_pct"] == 100

    out_row = {
        "record_id": returned.record_id,
        "unit_id": returned.unit_id,
        "org_id": returned.org_id,
        "order_id": returned.order_id,
        "ordered_sku": returned.ordered_sku,
        "ordered_asin": returned.ordered_asin,
        "identity_match": "uncertain",
        "parts_list": before.parts_list,
        "parts_missing": "",
        "observed_state": "uncertain",
        "amazon_condition": "uncertain",
        "operator_disposition": "pending_review",
        "photo_refs": ";".join(returned.returned_photo_refs),
        "captured_at": returned.time,
        "sold_vs_returned_id_check": "matched",
    }
    detail = _build_synthetic_row_detail(out_row, before, returned)
    assert out_row["operator_disposition"] == "restock"
    assert out_row["amazon_condition"] == "Used - Like New"
    assert detail["decision"]["recommended_disposition"] == "restock"
    assert detail["decision"]["auto_approved"] is True
    assert detail["decision"]["requires_review"] is False
    assert detail["similarity"]["confidence"] >= 85


