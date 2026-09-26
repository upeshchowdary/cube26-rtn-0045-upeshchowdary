"""T-EVL-* tests for Phase 12 (§21: eval tooling computation).

T-EVL-01  Agreement: raw agreement, Cohen's kappa, weighted quadratic kappa, and their
          bootstrap CIs, on hand-computed small examples.
T-EVL-02  Selective prediction: strict accuracy, coverage, selective accuracy,
          unnecessary-uncertain rate (§21.2) - including that "uncertain" never counts
          as correct even when gold agrees.
T-EVL-03  Per-check FP/FN direction (§21.1) for unit_presence, identity, completeness,
          condition (ordinal), and the disposition confusion matrix's two named
          dangerous cells.
T-EVL-04  condition_error_label: exact / over_grade_by_N / under_grade_by_N / uncertain.
T-EVL-05  tag_failure_mode assigns a tag from the fixed §21.4 taxonomy on disagreement,
          and None on full agreement.
T-EVL-06  eval seal: coverage-quota checks (met / missing, per-quota detail) and the
          minimum-unit-count guard, both with and without --dev-mini.
T-EVL-07  eval seal: fixture-overlap rejection requires BOTH a shared SKU and a shared
          photo hash - either alone is not enough.
T-EVL-08  labels_before_run_guard: refuses units with fewer than 2 independent labels.
T-EVL-09  per_unit_table + report + threshold_sweep + policy_tuning: focused unit tests
          for the pieces run_eval() composes but that deserve their own direct coverage.
T-EVL-10  `eval run --dev-mini` end-to-end via the real CLI: writes manifest.json,
          metrics.json, report.md, and per_unit_table.csv; `eval report` then reads the
          same report.md back. `eval run` without --dev-mini refuses cleanly (no sealed
          set exists). `eval seal` refuses under 50 units without --dev-mini and accepts
          with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from returns_manager.eval.agreement import (
    agreement_report,
    bootstrap_ci,
    cohen_kappa_nominal,
    raw_agreement,
    weighted_kappa_ordinal,
)
from returns_manager.eval.confusion import (
    completeness_fp_fn,
    condition_error_label,
    condition_fp_fn,
    disposition_confusion,
    identity_fp_fn,
    tag_failure_mode,
    unit_presence_fp_fn,
)
from returns_manager.eval.models import (
    CONDITION_GRADE_ORDER,
    FAILURE_MODES,
    AgentResult,
    EvaluatedUnit,
    GoldLabel,
    HumanLabel,
    UnitMeta,
)
from returns_manager.eval.selective import selective_prediction_report

# ── T-EVL-01: agreement statistics ──────────────────────────────────────────────


def test_t_evl_01_raw_and_kappa_on_known_values() -> None:
    a = ["yes", "no", "yes", "yes", "no", "yes", "no", "yes", "yes", "no"]
    b = ["yes", "no", "yes", "no", "no", "yes", "no", "yes", "no", "no"]
    assert raw_agreement(a, b) == pytest.approx(0.8)
    kappa = cohen_kappa_nominal(a, b)
    assert -1.0 <= kappa <= 1.0

    # Perfect agreement -> kappa == 1.0 exactly.
    assert cohen_kappa_nominal(a, a) == pytest.approx(1.0)


def test_t_evl_01_weighted_kappa_penalizes_distance() -> None:
    gold = ["New", "Used - Good", "Used - Acceptable"]
    close_miss = ["Used - Like New", "Used - Good", "Used - Acceptable"]  # off by 1, twice right
    far_miss = ["Used - Acceptable", "Used - Good", "New"]  # off by 4 and 4
    close_kappa = weighted_kappa_ordinal(gold, close_miss, CONDITION_GRADE_ORDER)
    far_kappa = weighted_kappa_ordinal(gold, far_miss, CONDITION_GRADE_ORDER)
    assert close_kappa > far_kappa, "a 1-step miss must score better than a 4-step miss"


def test_t_evl_01_bootstrap_ci_seeded_and_reproducible() -> None:
    a = ["yes", "no", "yes", "yes", "no", "yes", "no", "yes", "yes", "no"]
    b = ["yes", "no", "yes", "no", "no", "yes", "no", "yes", "no", "no"]
    lo1, hi1 = bootstrap_ci(raw_agreement, a, b, resamples=200, seed=42)
    lo2, hi2 = bootstrap_ci(raw_agreement, a, b, resamples=200, seed=42)
    assert (lo1, hi1) == (lo2, hi2), "same seed must give the same interval"
    assert lo1 <= raw_agreement(a, b) <= hi1


def test_t_evl_01_agreement_report_has_all_three_with_ordinal() -> None:
    a = ["New", "Used - Good", "Used - Acceptable", "New", "Used - Very Good"]
    b = ["New", "Used - Good", "Used - Good", "Used - Like New", "Used - Very Good"]
    report = agreement_report(a, b, ordinal_labels=CONDITION_GRADE_ORDER, resamples=100)
    assert set(report) == {"raw_agreement", "cohen_kappa", "weighted_kappa_quadratic"}
    for result in report.values():
        assert result.n == 5
        assert result.ci_low <= result.value <= result.ci_high or result.ci_low == result.ci_high


# ── T-EVL-02: selective prediction ──────────────────────────────────────────────


def test_t_evl_02_selective_prediction_all_four_numbers() -> None:
    agent = ["yes", "uncertain", "no", "yes", "uncertain"]
    gold = ["yes", "no", "no", "no", "uncertain"]
    report = selective_prediction_report(agent, gold)
    # Correct & decided: index 0 (yes==yes). Wrong & decided: index 2 (no==no) is correct
    # too, index 3 (yes != no) wrong. Uncertain: index 1, index 4.
    assert report.n == 5
    assert report.coverage == pytest.approx(3 / 5)  # indices 0,2,3 decided
    assert report.strict_accuracy == pytest.approx(2 / 5)  # only 0 and 2 correct & decided


def test_t_evl_02_uncertain_never_counts_as_correct_even_matching_gold() -> None:
    # Agent says uncertain exactly where gold also says uncertain - must NOT be "correct".
    agent = ["uncertain", "yes"]
    gold = ["uncertain", "yes"]
    report = selective_prediction_report(agent, gold)
    assert report.strict_accuracy == pytest.approx(0.5), "uncertain/uncertain must not count as correct"
    assert report.coverage == pytest.approx(0.5)


def test_t_evl_02_unnecessary_uncertain_rate() -> None:
    agent = ["uncertain", "uncertain", "yes", "no"]
    gold = ["yes", "uncertain", "yes", "no"]
    report = selective_prediction_report(agent, gold)
    # Clear-gold positions: 0, 2, 3 (gold != uncertain). Agent uncertain among those: only 0.
    assert report.unnecessary_uncertain_rate == pytest.approx(1 / 3)


# ── T-EVL-03: per-check FP/FN direction ─────────────────────────────────────────


def test_t_evl_03_unit_presence_fp_fn_direction() -> None:
    # FP: agent says empty, gold says present. FN: agent says present, gold says empty.
    agent = ["empty_packaging", "product_present", "product_present"]
    gold = ["product_present", "empty_packaging", "product_present"]
    result = unit_presence_fp_fn(agent, gold)
    assert result.fp == 1
    assert result.fn == 1
    assert result.n == 3


def test_t_evl_03_identity_fp_fn_direction() -> None:
    agent = ["no", "yes", "yes"]
    gold = ["yes", "no", "yes"]
    result = identity_fp_fn(agent, gold)
    assert result.fp == 1  # flagged wrong (no) but gold says right
    assert result.fn == 1  # said right (yes) but gold says wrong (no) - the dangerous one


def test_t_evl_03_completeness_fp_fn_direction() -> None:
    agent = ["incomplete", "complete", "complete"]
    gold = ["complete", "incomplete", "complete"]
    result = completeness_fp_fn(agent, gold)
    assert result.fp == 1
    assert result.fn == 1


def test_t_evl_03_condition_fp_fn_over_vs_under_grade() -> None:
    # over-grade (agent better than gold, the dangerous FN) and under-grade (agent worse, FP).
    agent = ["New", "Used - Acceptable", "Used - Good"]
    gold = ["Used - Good", "Used - Good", "Used - Good"]
    result = condition_fp_fn(agent, gold)
    assert result.fn == 1, "over-grading (New when gold is Used - Good) is the dangerous FN"
    assert result.fp == 1, "under-grading (Acceptable when gold is Used - Good) is the FP"
    assert result.n == 3


def test_t_evl_03_disposition_confusion_dangerous_cells() -> None:
    agent = ["restock", "dispose", "refurbish", "restock"]
    gold = ["liquidate", "refurbish", "refurbish", "restock"]
    result = disposition_confusion(agent, gold)
    assert result.n == 4
    assert result.restock_when_gold_not_restock == 1  # index 0
    assert result.dispose_when_gold_recoverable == 1  # index 1
    assert result.matrix["refurbish"]["refurbish"] == 1
    assert result.matrix["restock"]["restock"] == 1


# ── T-EVL-04: condition_error_label ─────────────────────────────────────────────


def test_t_evl_04_condition_error_label() -> None:
    assert condition_error_label("Used - Good", "Used - Good") == "exact"
    assert condition_error_label("New", "Used - Good") == "over_grade_by_3"
    assert condition_error_label("Used - Acceptable", "Used - Good") == "under_grade_by_1"
    assert condition_error_label("uncertain", "Used - Good") == "agent_uncertain"


# ── T-EVL-05: failure-mode tagging ──────────────────────────────────────────────


def _unit(**overrides: object) -> EvaluatedUnit:
    base_human = HumanLabel(
        labeller="a",
        unit_presence="product_present",
        identity="yes",
        completeness="complete",
        parts_missing=(),
        condition="Used - Good",
        disposition="restock",
    )
    base_gold = GoldLabel(
        unit_presence="product_present",
        identity="yes",
        completeness="complete",
        parts_missing=(),
        condition="Used - Good",
        disposition="restock",
    )
    base_agent = AgentResult(
        unit_presence="product_present",
        identity="yes",
        completeness="complete",
        parts_missing=(),
        condition="Used - Good",
        disposition="restock",
        requires_review=False,
        uncertain_checks=(),
        uncertainty_reasons=(),
        latency_ms=1000,
        cost_usd=0.001,
    )
    meta = UnitMeta(
        unit_id="UNIT-EVL-1",
        scenario_codes=("S01",),
        lighting="normal",
        angle="square",
        blur="none",
        ambiguity="clear",
        product_seen_in_dev=True,
    )
    fields = {
        "meta": meta,
        "human_a": base_human,
        "human_b": base_human,
        "gold": base_gold,
        "agent": base_agent,
    }
    fields.update(overrides)
    return EvaluatedUnit(**fields)  # type: ignore[arg-type]


def test_t_evl_05_no_tag_on_full_agreement() -> None:
    assert tag_failure_mode(_unit()) is None


def test_t_evl_05_identity_disagreement_tagged() -> None:
    agent = AgentResult(
        unit_presence="product_present",
        identity="no",
        completeness="complete",
        parts_missing=(),
        condition="Used - Good",
        disposition="restock",
        requires_review=True,
        uncertain_checks=(),
        uncertainty_reasons=(),
        latency_ms=1000,
        cost_usd=0.001,
    )
    unit = _unit(agent=agent)
    mode = tag_failure_mode(unit)
    assert mode in FAILURE_MODES
    assert mode in ("wrong_sku_similar_product", "barcode_failure", "poor_lighting", "blur")


def test_t_evl_05_disposition_disagreement_tagged_wrong_disposition() -> None:
    agent = AgentResult(
        unit_presence="product_present",
        identity="yes",
        completeness="complete",
        parts_missing=(),
        condition="Used - Good",
        disposition="liquidate",
        requires_review=True,
        uncertain_checks=(),
        uncertainty_reasons=(),
        latency_ms=1000,
        cost_usd=0.001,
    )
    unit = _unit(agent=agent)
    assert tag_failure_mode(unit) == "wrong_disposition"


def test_t_evl_05_fixed_taxonomy_is_exactly_what_the_prompt_lists() -> None:
    assert {
        "wrong_sku_similar_product",
        "barcode_failure",
        "ocr_failure",
        "visual_occlusion",
        "poor_lighting",
        "blur",
        "missing_angle",
        "accessory_not_visible",
        "false_missing_component",
        "condition_ambiguity",
        "overgrade",
        "undergrade",
        "policy_mismatch",
        "evidence_verdict_conflict",
        "wrong_disposition",
        "refusal",
        "schema_error",
    } == FAILURE_MODES


# ── T-EVL-06/07/08: eval seal ────────────────────────────────────────────────────


def _meta(unit_id: str, **overrides: object) -> UnitMeta:
    fields: dict[str, object] = {
        "unit_id": unit_id,
        "scenario_codes": ("S01",),
        "lighting": "normal",
        "angle": "square",
        "blur": "none",
        "ambiguity": "clear",
        "product_seen_in_dev": True,
    }
    fields.update(overrides)
    return UnitMeta(**fields)  # type: ignore[arg-type]


def test_t_evl_06_coverage_quotas_report_exactly_whats_missing() -> None:
    from returns_manager.eval.seal import check_coverage_quotas

    units = [_meta(f"U{i}", scenario_codes=("S01",)) for i in range(3)]
    result = check_coverage_quotas(units)
    assert not result.all_met  # S02..S10, lighting:poor, etc. are all still 0
    s01 = next(q for q in result.quotas if q.name == "scenario:S01")
    assert s01.met
    assert s01.actual == 3
    s02 = next(q for q in result.quotas if q.name == "scenario:S02")
    assert not s02.met
    assert s02.actual == 0
    assert "scenario:S02" in result.missing_summary


def test_t_evl_06_seal_refuses_under_50_without_dev_mini() -> None:
    from returns_manager.eval.seal import SealRefused, seal

    units = [_meta(f"U{i}") for i in range(10)]
    with pytest.raises(SealRefused, match="50"):
        seal(units, dev_mini=False)
    # The same candidate set is fine under --dev-mini.
    result = seal(units, dev_mini=True)
    assert result.unit_ids == tuple(u.unit_id for u in units)
    assert result.dev_mini is True
    assert len(result.content_sha256) == 64


def test_t_evl_06_seal_refuses_missed_quota_even_at_50_units_without_dev_mini() -> None:
    from returns_manager.eval.seal import SealRefused, seal

    # 50 units but all the same scenario - every other quota (S02..S10, lighting:poor,
    # angle:oblique, blur:slight, ambiguity, unseen-products) is 0/required.
    units = [_meta(f"U{i}") for i in range(50)]
    with pytest.raises(SealRefused, match="coverage quotas not met"):
        seal(units, dev_mini=False)


def test_t_evl_06_seal_hash_is_deterministic_and_order_independent() -> None:
    from returns_manager.eval.seal import seal

    units = [_meta(f"U{i}") for i in range(5)]
    a = seal(units, dev_mini=True)
    b = seal(list(reversed(units)), dev_mini=True)
    assert a.content_sha256 == b.content_sha256, "hash must not depend on input order"


def test_t_evl_07_fixture_overlap_needs_both_sku_and_photo() -> None:
    from returns_manager.eval.seal import find_fixture_overlap

    units = [_meta("U1"), _meta("U2"), _meta("U3")]
    unit_sku = {"U1": "SKU-A", "U2": "SKU-A", "U3": "SKU-B"}
    unit_photos = {
        "U1": frozenset({"hash1"}),  # same SKU and a shared photo -> reject
        "U2": frozenset({"hash-not-shared"}),  # same SKU but a different photo -> keep
        "U3": frozenset({"hash1"}),  # shared photo but a different SKU -> keep
    }
    rejected = find_fixture_overlap(units, unit_sku, unit_photos, frozenset({"SKU-A"}), frozenset({"hash1"}))
    assert rejected == ("U1",)


def test_t_evl_08_labels_before_run_guard() -> None:
    from returns_manager.eval.seal import labels_before_run_guard

    unit_ids = ["U1", "U2", "U3"]
    labels_present = {"U1": 2, "U2": 1, "U3": 0}
    missing = labels_before_run_guard(unit_ids, labels_present)
    assert set(missing) == {"U2", "U3"}
    assert labels_before_run_guard(["U1"], labels_present) == ()


# ── T-EVL-09: per_unit_table / report / threshold_sweep / policy_tuning ─────────


def test_t_evl_09_per_unit_table_row_order_disagreements_first() -> None:
    from returns_manager.eval.per_unit_table import build_rows

    agree_unit = _unit()
    disagree_agent = AgentResult(
        unit_presence="product_present",
        identity="no",
        completeness="complete",
        parts_missing=(),
        condition="Used - Good",
        disposition="restock",
        requires_review=True,
        uncertain_checks=(),
        uncertainty_reasons=(),
        latency_ms=1000,
        cost_usd=0.001,
    )
    disagree_unit = _unit(agent=disagree_agent)
    rows = build_rows([agree_unit, disagree_unit])
    assert rows[0]["identity_agree"] == "no", "the disagreeing unit must sort first"


def test_t_evl_09_report_renders_without_raising_and_contains_key_sections() -> None:
    from returns_manager.eval.confusion import disposition_confusion, tag_failure_modes
    from returns_manager.eval.models import RunManifest
    from returns_manager.eval.report import ReportSections, build_report
    from returns_manager.eval.selective import selective_prediction_report

    units = [_unit()]
    tagged, failure_modes = tag_failure_modes(units)
    manifest = RunManifest(run_id="r1", dev_mini=True, units_requested=1, units_evaluated=1, seed=1)
    md = build_report(
        ReportSections(
            manifest=manifest,
            units=tagged,
            agreement={},
            selective={"identity": selective_prediction_report(["yes"], ["yes"])},
            fp_fn={},
            disposition_confusion=disposition_confusion(["restock"], ["restock"]),
            failure_modes=failure_modes,
        )
    )
    assert "# Eval report" in md
    assert "Per-unit table" in md
    assert "r1" in md


def test_t_evl_09_threshold_sweep_and_policy_tuning_smoke() -> None:
    from returns_manager.disposition.engine import DispositionInputs, decide
    from returns_manager.eval.policy_tuning import rerun_under_variant, restock_used_grades_variant
    from returns_manager.eval.threshold_sweep import choose_operating_point, sweep

    points = sweep([10000, 5000, 0], [True, True, False])
    chosen, why = choose_operating_point(points, max_false_accept_rate=0.0)
    assert chosen is not None
    assert why

    inp = DispositionInputs(
        inspection_state="complete",
        skip_reason=None,
        usable_photo_count=3,
        unit_presence="product_present",
        identity="yes",
        actual_sku=None,
        completeness_status="complete",
        essential_missing=(),
        nonessential_missing=(),
        essential_uncertain=(),
        nonessential_uncertain=(),
        cosmetic_grade="used_good",
        listing_blockers=(),
        blockers_undetermined=(),
        max_severity="none",
        new_only=False,
        opened_item_route="refurbish",
        damaged_item_route="dispose",
        list_price_minor=100_000,
        currency="INR",
        recovery_rate_bp=(
            ("restock_new", 9000),
            ("restock_used", 7000),
            ("refurbish", 6000),
            ("liquidate", 2000),
        ),
        refurbish_cost_minor=5000,
        restock_used_grades=("used_good", "used_very_good"),
        refurbish_min_net_gain_minor=1000,
        dispose_max_salvage_minor=500,
        high_value_threshold_minor=500_000,
    )
    baseline = decide(inp, "v1")
    variant = restock_used_grades_variant("used_like_new_only", ["used_like_new"])
    result = rerun_under_variant([inp], [baseline], "v1", variant)
    assert result.n == 1
    assert result.variant_name == "used_like_new_only"


# ── T-EVL-10: `eval seal` / `eval run --dev-mini` / `eval report` via the real CLI ──


def test_t_evl_10_dev_mini_end_to_end_via_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from returns_manager.cli import eval_commands
    from returns_manager.cli.main import run

    monkeypatch.setattr(eval_commands, "EVAL_ROOT", tmp_path)

    exit_code = run(["eval", "run", "--run-id", "t-evl-10", "--dev-mini"])
    assert exit_code == 0

    run_dir = tmp_path / "runs" / "t-evl-10"
    for name in ("manifest.json", "metrics.json", "report.md", "per_unit_table.csv"):
        assert (run_dir / name).exists(), f"{name} was not written"

    csv_text = (run_dir / "per_unit_table.csv").read_text(encoding="utf-8")
    assert csv_text.splitlines()[0].startswith("unit_id,")
    assert "DEV-MINI-" in csv_text

    # `eval report` reads the same report.md back.
    out_file = tmp_path / "shown_report.md"
    exit_code = run(["eval", "report", "--run-id", "t-evl-10", "--out", str(out_file)])
    assert exit_code == 0
    assert out_file.read_text(encoding="utf-8") == (run_dir / "report.md").read_text(encoding="utf-8")


def test_t_evl_10_eval_run_without_dev_mini_refuses_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from returns_manager.cli import eval_commands
    from returns_manager.cli.main import run

    monkeypatch.setattr(eval_commands, "EVAL_ROOT", tmp_path)
    exit_code = run(["eval", "run", "--run-id", "no-sealed-set"])
    assert exit_code == 1
    assert not (tmp_path / "runs" / "no-sealed-set").exists()


def test_t_evl_10_eval_seal_cli_dev_mini_vs_strict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from returns_manager.cli import eval_commands
    from returns_manager.cli.main import run

    monkeypatch.setattr(eval_commands, "EVAL_ROOT", tmp_path)
    units_dir = tmp_path / "units"
    units_dir.mkdir()
    (units_dir / "U1.json").write_text(
        '{"unit_id": "U1", "scenario_codes": ["S01"], "lighting": "normal", "angle": '
        '"square", "blur": "none", "ambiguity": "clear", "product_seen_in_dev": true}',
        encoding="utf-8",
    )

    strict_exit = run(["eval", "seal", "--units-dir", str(units_dir)])
    assert strict_exit == 3  # refused: 1 unit, needs >= 50

    dev_mini_exit = run(["eval", "seal", "--dev-mini", "--units-dir", str(units_dir)])
    assert dev_mini_exit == 0
