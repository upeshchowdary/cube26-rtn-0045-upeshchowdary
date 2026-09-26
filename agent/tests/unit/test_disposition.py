"""Disposition engine (§12; P6): rule-table tests, property invariants, sign-off and data traps."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from returns_manager.disposition.engine import (
    ROUTE_RANK,
    DispositionInputs,
    MissingPart,
    decide,
)
from returns_manager.disposition.params import load_params, rules_version

RV = "disposition-test"
RATES = (
    ("dispose", 0),
    ("liquidate", 2000),
    ("refurbish", 5500),
    ("restock_new", 10000),
    ("restock_used", 6500),
)


def inputs(**changes: Any) -> DispositionInputs:
    base = DispositionInputs(
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
        cosmetic_grade="used_like_new",
        listing_blockers=(),
        blockers_undetermined=(),
        max_severity="none",
        new_only=False,
        opened_item_route="restock",
        damaged_item_route="liquidate",
        list_price_minor=199900,
        currency="INR",
        recovery_rate_bp=RATES,
        refurbish_cost_minor=30000,
        restock_used_grades=("used_like_new", "used_very_good"),
        refurbish_min_net_gain_minor=10000,
        dispose_max_salvage_minor=5000,
        high_value_threshold_minor=500000,
    )
    return replace(base, **changes)


CABLE = MissingPart("usb_cable", True)
LAMP = MissingPart("lamp", False)


# ── Step 1 gates ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("changes", "rule", "reason"),
    [
        ({"inspection_state": "incomplete"}, "R01", "inspection_incomplete"),
        ({"usable_photo_count": 0}, "R01", "inspection_incomplete"),
        (
            {"inspection_state": "skipped", "skip_reason": "no_product_reference"},
            "R01b",
            "no_product_reference",
        ),
        ({"unit_presence": "empty_packaging"}, "R02", "item_not_present_or_unverified"),
        ({"unit_presence": "non_product_contents"}, "R02", "item_not_present_or_unverified"),
        ({"unit_presence": "uncertain"}, "R02", "item_not_present_or_unverified"),
        ({"identity": "no", "actual_sku": "SKU-X"}, "R03", "wrong_item_returned"),
        ({"identity": "uncertain"}, "R03b", "identity_unverified"),
        ({"cosmetic_grade": None}, "R05b", "condition_uncertain"),
    ],
)
def test_t_dsp_gates_blank_the_recommendation(changes: dict[str, Any], rule: str, reason: str) -> None:
    d = decide(inputs(**changes), RV)
    assert d.recommended_disposition is None
    assert d.rule_id == rule
    assert d.no_recommendation_reason == reason
    assert d.requires_review
    assert reason in d.review_reasons


def test_t_dsp_r03_records_the_actual_sku() -> None:
    d = decide(inputs(identity="no", actual_sku="SKU-LAMP-LED-V2"), RV)
    assert "actual_sku:SKU-LAMP-LED-V2" in d.reasons


def test_t_dsp_r05b_not_applied_when_a_blocker_decides_alone() -> None:
    d = decide(inputs(cosmetic_grade=None, listing_blockers=("consumable_used",)), RV)
    assert d.recommended_disposition == "dispose"
    assert d.rule_id == "R08"


# ── Step 2 flags: review without blanking ─────────────────────────────────
def test_t_dsp_r00_assisted_mode_keeps_the_suggestion() -> None:
    d = decide(inputs(auto_disposition_enabled=False), RV)
    assert d.recommended_disposition == "restock"
    assert d.requires_review
    assert "assisted_mode" in d.review_reasons


@pytest.mark.parametrize(
    "flag",
    ["injection_attempt_suspected", "audit_disagreement", "model_disagreement", "possible_reused_photo"],
)
def test_t_dsp_r04_flags_require_review(flag: str) -> None:
    d = decide(inputs(flags=(flag,)), RV)
    assert d.recommended_disposition == "restock"
    assert d.requires_review
    assert flag in d.review_reasons


def test_t_dsp_r05_uncertain_essential_is_provisional_and_assumed_missing() -> None:
    d = decide(
        inputs(
            essential_uncertain=(CABLE,),
            completeness_status="uncertain",
            listing_blockers=("functional_test_required",),
        ),
        RV,
    )
    assert d.provisional
    assert d.requires_review
    assert d.assumptions
    assert "essential_component_uncertain" in d.review_reasons
    assert d.recommended_disposition == "refurbish"  # computed as if the cable were missing (R09)
    assert d.rule_id == "R09"


def test_t_dsp_r05c_nonessential_uncertain_and_undetermined_blockers() -> None:
    d = decide(
        inputs(nonessential_uncertain=("manual",), blockers_undetermined=("category_new_only_opened",)), RV
    )
    assert d.recommended_disposition is not None
    assert {"nonessential_component_uncertain", "listing_blockers_undetermined"} <= set(d.review_reasons)


# ── Step 3 route rules ────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("changes", "route", "rule", "listing"),
    [
        ({"new_only": True, "cosmetic_grade": "new"}, "restock", "R06", "new"),
        (
            {
                "new_only": True,
                "cosmetic_grade": "used_like_new",
                "listing_blockers": ("category_new_only_opened",),
                "opened_item_route": "dispose",
                "damaged_item_route": "dispose",
            },
            "dispose",
            "R07",
            None,
        ),
        (
            {
                "new_only": True,
                "cosmetic_grade": None,
                "listing_blockers": ("category_new_only_opened",),
                "opened_item_route": "liquidate",
                "damaged_item_route": "dispose",
            },
            "liquidate",
            "R07",
            None,
        ),
        (
            {
                "new_only": True,
                "cosmetic_grade": None,
                "max_severity": "severe",
                "listing_blockers": ("category_new_only_opened", "damaged_difficult_to_use"),
                "opened_item_route": "liquidate",
                "damaged_item_route": "dispose",
            },
            "dispose",
            "R07",
            None,
        ),
        ({"listing_blockers": ("consumable_used",)}, "dispose", "R08", None),
        (
            {
                "essential_missing": (CABLE,),
                "completeness_status": "incomplete",
                "listing_blockers": ("essential_component_missing", "functional_test_required"),
            },
            "refurbish",
            "R09",
            None,
        ),
        (
            {
                "essential_missing": (LAMP,),
                "completeness_status": "incomplete",
                "listing_blockers": ("essential_component_missing",),
            },
            "liquidate",
            "R10",
            None,
        ),
        (
            {"listing_blockers": ("damaged_difficult_to_use",), "max_severity": "severe"},
            "liquidate",
            "R10",
            None,
        ),
        ({"listing_blockers": ("not_clean",)}, "liquidate", "R10", None),
        (
            {"listing_blockers": ("functional_test_required",), "cosmetic_grade": "used_good"},
            "refurbish",
            "R11",
            None,
        ),
        ({"cosmetic_grade": "new"}, "restock", "R12", "new"),
        ({"cosmetic_grade": "used_very_good"}, "restock", "R13", "used_very_good"),
        ({"cosmetic_grade": "used_good"}, "liquidate", "R14", None),
        ({"cosmetic_grade": "used_acceptable"}, "liquidate", "R14", None),
        (
            {
                "cosmetic_grade": "used_like_new",
                "completeness_status": "incomplete",
                "nonessential_missing": ("manual",),
            },
            "liquidate",
            "R14",
            None,
        ),
    ],
)
def test_t_dsp_route_rules(changes: dict[str, Any], route: str, rule: str, listing: str | None) -> None:
    d = decide(inputs(**changes), RV)
    assert (d.recommended_disposition, d.rule_id, d.listing_condition) == (route, rule, listing)


def test_t_dsp_r10_low_salvage_disposes_with_signoff() -> None:
    cheap = inputs(
        list_price_minor=20000, listing_blockers=("damaged_difficult_to_use",), max_severity="severe"
    )
    d = decide(cheap, RV)  # liquidate recovery 4000 <= dispose_max_salvage 5000
    assert d.recommended_disposition == "dispose"
    assert d.requires_signoff
    assert "S01_dispose_always" in d.signoff_reasons


def test_t_dsp_r11_small_margin_liquidates() -> None:
    d = decide(inputs(list_price_minor=40000, listing_blockers=("functional_test_required",)), RV)
    assert d.recommended_disposition == "liquidate"
    assert d.rule_id == "R11"


def test_t_dsp_r09_not_when_the_complete_item_would_be_liquidated() -> None:
    """F-012: a missing replaceable part must not upgrade a liquidate-grade item to refurbish."""
    d = decide(
        inputs(cosmetic_grade="used_good", essential_missing=(CABLE,), completeness_status="incomplete"), RV
    )
    assert d.recommended_disposition in ("liquidate", "dispose")
    assert d.rule_id == "R10"


def test_t_dsp_r99_policy_conflict_is_null_with_review() -> None:
    d = decide(
        inputs(
            new_only=True,
            cosmetic_grade=None,
            listing_blockers=("category_new_only_opened",),
            opened_item_route="restock",
        ),
        RV,
    )
    assert d.recommended_disposition is None
    assert d.rule_id == "R99"
    assert d.requires_review


# ── sign-off ──────────────────────────────────────────────────────────────
def test_t_dsp_s02_high_value_non_restock_needs_signoff() -> None:
    d = decide(inputs(list_price_minor=900000, cosmetic_grade="used_good"), RV)
    assert d.recommended_disposition == "liquidate"
    assert "S02_high_value" in d.signoff_reasons
    restock = decide(inputs(list_price_minor=900000), RV)
    assert not restock.requires_signoff


def test_t_dsp_s03_escalation_disagreement_needs_signoff() -> None:
    d = decide(inputs(escalation_disagreement_resolved_by_reviewer=True), RV)
    assert "S03_escalation_disagreement_resolved" in d.signoff_reasons


# ── sample-data traps (findings F-002, F-003) ─────────────────────────────
def test_trap_rtn_0030_0081_opened_consumable_never_restocked_or_refurbished() -> None:
    for routes in (("dispose", "dispose"),):  # beauty_topical and grocery_ingestible policies
        d = decide(
            inputs(
                new_only=True,
                cosmetic_grade=None,
                listing_blockers=("category_new_only_opened",),
                opened_item_route=routes[0],
                damaged_item_route=routes[1],
            ),
            RV,
        )
        assert d.recommended_disposition == "dispose"


def test_trap_rtn_0097_used_protein_never_refurbished() -> None:
    d = decide(
        inputs(
            new_only=True,
            cosmetic_grade=None,
            completeness_status="incomplete",
            nonessential_missing=("scoop",),
            listing_blockers=("category_new_only_opened", "consumable_used"),
            opened_item_route="dispose",
            damaged_item_route="dispose",
        ),
        RV,
    )
    assert d.recommended_disposition not in ("restock", "refurbish")


def test_trap_rtn_0038_missing_tub_never_restocked() -> None:
    tub = MissingPart("tub", False)
    for new_only in (True, False):
        d = decide(
            inputs(
                new_only=new_only,
                essential_missing=(tub,),
                completeness_status="incomplete",
                listing_blockers=("essential_component_missing",),
                opened_item_route="dispose",
                damaged_item_route="dispose",
            ),
            RV,
        )
        assert d.recommended_disposition != "restock"


# ── determinism, versioning ───────────────────────────────────────────────
def test_same_inputs_same_output_and_hash() -> None:
    a, b = decide(inputs(), RV), decide(inputs(), RV)
    assert a == b
    assert a.inputs_sha256 == inputs().sha256()
    assert inputs(cosmetic_grade="used_good").sha256() != a.inputs_sha256


def test_canonical_round_trip_for_simulation() -> None:
    inp = inputs(
        essential_missing=(CABLE,), flags=("possible_reused_photo",), nonessential_uncertain=("manual",)
    )
    assert DispositionInputs.from_canonical(inp.canonical()) == inp


def test_rules_version_is_derived_from_engine_and_params() -> None:
    v = rules_version(load_params())
    assert v.startswith("disposition-")
    assert len(v) == len("disposition-") + 12


# ── §12.3 invariants (property tests) ─────────────────────────────────────
GRADES = st.sampled_from([None, "new", "used_like_new", "used_very_good", "used_good", "used_acceptable"])
BLOCKERS = [
    "damaged_difficult_to_use",
    "not_clean",
    "functional_test_required",
    "category_new_only_opened",
    "consumable_used",
]
ROUTES = st.sampled_from(["liquidate", "dispose"])


@st.composite
def any_inputs(draw: st.DrawFn) -> DispositionInputs:
    new_only = draw(st.booleans())
    ess_missing = tuple(draw(st.lists(st.sampled_from([CABLE, LAMP]), unique=True, max_size=2)))
    ess_unsure = tuple(
        p
        for p in draw(st.lists(st.sampled_from([CABLE, LAMP]), unique=True, max_size=2))
        if p not in ess_missing
    )
    blockers = set(draw(st.lists(st.sampled_from(BLOCKERS), unique=True, max_size=3)))
    if ess_missing:
        blockers.add("essential_component_missing")
    non_missing = tuple(draw(st.lists(st.just("manual"), max_size=1)))
    status = "incomplete" if (ess_missing or non_missing) else ("uncertain" if ess_unsure else "complete")
    opened = draw(ROUTES)
    damaged = "dispose" if opened == "dispose" else draw(ROUTES)  # policies never make damage a better route
    return inputs(
        inspection_state=draw(st.sampled_from(["complete", "complete", "complete", "incomplete", "skipped"])),
        skip_reason="no_product_reference",
        unit_presence=draw(
            st.sampled_from(["product_present", "product_present", "empty_packaging", "uncertain"])
        ),
        identity=draw(st.sampled_from(["yes", "yes", "yes", "no", "uncertain"])),
        completeness_status=status,
        essential_missing=ess_missing,
        essential_uncertain=ess_unsure,
        nonessential_missing=non_missing,
        cosmetic_grade=draw(GRADES),
        listing_blockers=tuple(sorted(blockers)),
        max_severity=draw(st.sampled_from(["none", "minor", "moderate", "severe"])),
        new_only=new_only,
        opened_item_route=opened,
        damaged_item_route=damaged,
        list_price_minor=draw(st.integers(1000, 2_000_000)),
        auto_disposition_enabled=draw(st.booleans()),
        flags=tuple(
            draw(
                st.lists(
                    st.sampled_from(["possible_reused_photo", "injection_attempt_suspected"]),
                    unique=True,
                    max_size=1,
                )
            )
        ),
    )


@settings(max_examples=400, deadline=None)
@given(any_inputs())
def test_property_invariants(inp: DispositionInputs) -> None:
    d = decide(inp, RV)
    if inp.identity != "yes":
        assert d.recommended_disposition != "restock"
    if inp.new_only and d.recommended_disposition == "restock":
        assert d.listing_condition == "new"
    if d.recommended_disposition == "dispose":
        assert d.requires_signoff
    if not inp.auto_disposition_enabled:
        assert d.requires_review
    if d.recommended_disposition is None:
        assert d.requires_review
        assert d.no_recommendation_reason
    if d.provisional:
        assert d.requires_review
        assert d.assumptions
    assert decide(inp, RV) == d


@settings(max_examples=400, deadline=None)
@given(any_inputs(), st.sampled_from([CABLE, LAMP]))
def test_property_monotonic_in_missing_parts(inp: DispositionInputs, part: MissingPart) -> None:
    """Making a component go from present to missing never improves the route (review is neutral)."""
    if part in inp.essential_missing or part in inp.essential_uncertain:
        return
    worse = replace(
        inp,
        essential_missing=(*inp.essential_missing, part),
        completeness_status="incomplete",
        listing_blockers=tuple(sorted(set(inp.listing_blockers) | {"essential_component_missing"})),
    )
    a, b = decide(inp, RV).recommended_disposition, decide(worse, RV).recommended_disposition
    if a is not None and b is not None:
        assert ROUTE_RANK[b] <= ROUTE_RANK[a], (a, b)


@settings(max_examples=400, deadline=None)
@given(any_inputs())
def test_property_monotonic_in_severity(inp: DispositionInputs) -> None:
    """Worsening defect severity to 'severe' (which makes the item hard to use) never improves the route."""
    worse = replace(
        inp,
        max_severity="severe",
        listing_blockers=tuple(sorted(set(inp.listing_blockers) | {"damaged_difficult_to_use"})),
    )
    a, b = decide(inp, RV).recommended_disposition, decide(worse, RV).recommended_disposition
    if a is not None and b is not None:
        assert ROUTE_RANK[b] <= ROUTE_RANK[a], (a, b)
