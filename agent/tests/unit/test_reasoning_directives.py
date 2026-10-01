"""The reasoning directives (`REASONING_AGENT_MASTER_PROMPT.md`) and the review fixes made with them.

Each test names the directive or flaw it pins. Engine-level tests use the disposition test inputs;
pipeline-level tests run a crafted judgment through validation, consistency, fusion, grading and the engine.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from pydantic import ValidationError

from returns_manager.disposition.engine import decide
from returns_manager.judgment.pipeline import SINGLE_PHOTO_NOTE, calibrate_single_photo
from returns_manager.llm.schemas import JudgmentV1, repair_judgment_payload
from tests.unit import judgment_builders as b
from tests.unit.test_disposition import CABLE, RV, inputs

LAMP = b.card("org_demo_alpha", "SKU-LAMP-LED")


def _edit(j: JudgmentV1, fn: Any) -> JudgmentV1:
    data = j.model_dump()
    fn(data)
    return JudgmentV1.model_validate(data)


# ── F-018: a cosmetic schema slip must not throw away a whole inspection ─────────────────────────


def test_repair_trims_long_text_and_drops_an_invalid_box_without_touching_verdicts() -> None:
    raw = b.judgment(b.context(LAMP)).model_dump(mode="json")
    raw["identity"]["evidence"][0]["observation"] = "x" * 260
    raw["condition"]["observations"] = [{**b.defect("scratch"), "box_2d": [500, 100, 400, 300]}]
    with pytest.raises(ValidationError):
        JudgmentV1.model_validate(raw)

    fixed, fixes = repair_judgment_payload(raw)
    j = JudgmentV1.model_validate(fixed)
    assert len(j.identity.evidence[0].observation) == 200
    assert j.condition.observations[0].box_2d is None
    assert len(fixes) == 2
    assert j.identity.identity_match == raw["identity"]["identity_match"]
    assert raw["identity"]["evidence"][0]["observation"] == "x" * 260  # the original is not mutated


def test_repair_never_rescues_an_invalid_verdict() -> None:
    raw = b.judgment(b.context(LAMP)).model_dump(mode="json")
    raw["identity"]["identity_match"] = "probably"
    fixed, _ = repair_judgment_payload(raw)
    with pytest.raises(ValidationError):
        JudgmentV1.model_validate(fixed)


# ── Reference images describe what was sold, never what came back ───────────────────────────────


def test_a_defect_seen_only_on_the_reference_image_is_not_charged_to_the_return() -> None:
    ctx = b.context(LAMP)
    j = _edit(
        b.judgment(ctx), lambda d: d["condition"].update(observations=[b.defect("crack", "severe", "R1")])
    )
    r = b.run(ctx, j)
    assert r.condition.max_severity == "none"
    assert "damaged_difficult_to_use" not in r.condition.listing_blockers
    assert "REF-ONLY" in {a.rule_id for a in r.report.actions}


def test_a_part_seen_only_on_the_reference_image_is_not_present_on_the_return() -> None:
    ctx = b.context(LAMP)
    first = ctx.card.components[0].id
    j = b.component(ctx, b.judgment(ctx), first, status="present", photos=["R1"])
    r = b.run(ctx, j)
    assert next(c for c in r.completeness.components if c.component_id == first).status == "uncertain"


def test_crop_evidence_from_the_session_is_kept() -> None:
    ctx = dataclasses.replace(b.context(LAMP), crop_aliases=("C1",))
    j = _edit(
        b.judgment(ctx), lambda d: d["condition"].update(observations=[b.defect("scratch", "minor", "C1")])
    )
    assert b.run(ctx, j).condition.max_severity == "minor"


# ── Directive 1: single photograph ───────────────────────────────────────────────────────────────


def test_single_photo_is_judged_and_model_confidence_is_calibrated() -> None:
    ctx = b.context(LAMP, photos=("P1",))
    three = b.run(ctx, b.judgment(ctx), non_fail=3)
    one = b.run(ctx, b.judgment(ctx), non_fail=1)
    photo = next(c for c in one.checks if c.check_key == "photo_quality")
    assert photo.verdict == "PASS"
    assert photo.detail == SINGLE_PHOTO_NOTE
    by_key = {c.check_key: c for c in three.checks}
    for c in one.checks:
        if c.source == "model":
            assert c.confidence_bp == calibrate_single_photo(by_key[c.check_key].confidence_bp)
    assert calibrate_single_photo(10000) == 8500


# ── Directives 1/5/9: accessories out of frame ───────────────────────────────────────────────────


def test_a_clean_unit_with_accessories_out_of_frame_is_routed_not_left_in_a_rule_gap() -> None:
    d = decide(inputs(completeness_status="uncertain", essential_uncertain=(CABLE,)), RV)
    assert d.recommended_disposition == "restock"
    assert d.rule_id == "R13"
    assert d.provisional
    assert d.requires_review


# ── Directive 9: condition unknown on a used electrical item ─────────────────────────────────────


def test_unknown_condition_on_used_electrical_item_routes_to_technician_test() -> None:
    d = decide(inputs(cosmetic_grade=None, blockers_undetermined=("functional_test_required",)), RV)
    assert d.recommended_disposition == "refurbish"
    assert d.rule_id == "R05b+R11"
    assert d.provisional
    assert "condition_uncertain" in d.review_reasons


def test_unknown_condition_without_a_policy_route_still_has_no_route() -> None:
    d = decide(inputs(cosmetic_grade=None), RV)
    assert d.recommended_disposition is None
    assert d.no_recommendation_reason == "condition_uncertain"


# ── Directive 3: a proven variant mismatch is not undone by an uncertain observed state ──────────


def test_variant_mismatch_stays_a_wrong_item_when_observed_state_is_uncertain() -> None:
    ctx = b.context(LAMP)

    def wrong_variant(d: dict[str, Any]) -> None:
        d["identity"].update(identity_match="no", risk_flags=["variant_mismatch"])
        for fc in d["identity"]["feature_checks"]:
            fc["result"] = "mismatch"
        d["model_observed_state"] = "uncertain"

    r = b.run(ctx, _edit(b.judgment(ctx), wrong_variant))
    assert r.identity.identity_match == "no"
    assert r.decision.recommended_disposition == "dispose"
    assert r.decision.rule_id == "R03"


# ── Directive 7: the seal note states only what was observed ─────────────────────────────────────


def test_seal_note_only_when_an_opened_box_was_observed() -> None:
    opened = decide(inputs(flags=("packaging_opened",)), RV)
    unseen = decide(inputs(), RV)
    assert "box seal broken; internal unit pristine" in opened.reasons[0]
    assert "box seal" not in unseen.reasons[0]


def test_an_observed_opened_box_reaches_the_engine_as_a_flag() -> None:
    ctx = b.context(LAMP)  # the default crafted judgment has packaging_state opened_packaging_intact
    assert "packaging_opened" in b.run(ctx, b.judgment(ctx)).inputs.flags


# ── Directive 10: structural versus cosmetic damage ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("defect_type", "severity", "blocks"),
    [
        ("crack", "moderate", True),
        ("deformation", "moderate", True),
        ("water_damage", "severe", True),
        ("crack", "minor", False),
        ("scratch", "severe", False),
        ("scuff", "moderate", False),
        ("tear", "severe", True),
    ],
)
def test_structural_damage_blocks_listing_and_cosmetic_wear_does_not(
    defect_type: str, severity: str, blocks: bool
) -> None:
    ctx = b.context(LAMP)
    j = _edit(
        b.judgment(ctx), lambda d: d["condition"].update(observations=[b.defect(defect_type, severity)])
    )
    assert ("damaged_difficult_to_use" in b.run(ctx, j).condition.listing_blockers) is blocks
