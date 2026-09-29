"""Checks that every "Sample data" scenario on the landing page is one the real rules engine produces.

The landing page (ui/src/landing/sample.ts) shows engine outcomes for sample returns. This script feeds the
same inputs to `returns_manager.disposition.engine.decide` with the current parameters and category policies,
and fails if any outcome on the page (route, rule, review reasons, sign-off) differs from the engine's.

Run from agent/:  .venv/Scripts/python ../ui/sample-data/verify_samples.py   (or `uv run python ...`)
No model call, no database, no network.
"""

from __future__ import annotations

import sys

from returns_manager.batch.cards import (
    DEFAULT_RECOVERY_RATE_BP,
    DEFAULT_REFURBISH_COST_MINOR,
)
from returns_manager.batch.runner import load_policy
from returns_manager.disposition.engine import DispositionInputs, MissingPart, decide
from returns_manager.disposition.params import load_params, rules_version

PARAMS = load_params()
RULES_VERSION = rules_version(PARAMS)
RATES = tuple(DEFAULT_RECOVERY_RATE_BP.model_dump().items())


def inputs(category: str, **overrides: object) -> DispositionInputs:
    policy = load_policy(category)
    values: dict[str, object] = {
        "inspection_state": "complete",
        "skip_reason": None,
        "usable_photo_count": 3,
        "unit_presence": "product_present",
        "identity": "yes",
        "actual_sku": None,
        "completeness_status": "complete",
        "essential_missing": (),
        "nonessential_missing": (),
        "essential_uncertain": (),
        "nonessential_uncertain": (),
        "cosmetic_grade": "used_like_new",
        "listing_blockers": (),
        "blockers_undetermined": (),
        "max_severity": "none",
        "new_only": policy.new_only,
        "opened_item_route": policy.opened_item_route,
        "damaged_item_route": policy.damaged_item_route,
        "list_price_minor": 249900,  # INR 2,499, a sample price below the high-value threshold
        "currency": "INR",
        "recovery_rate_bp": RATES,
        "refurbish_cost_minor": DEFAULT_REFURBISH_COST_MINOR,
        "restock_used_grades": tuple(PARAMS.restock_used_grades),
        "refurbish_min_net_gain_minor": PARAMS.refurbish_min_net_gain.amount_minor,
        "dispose_max_salvage_minor": PARAMS.dispose_max_salvage.amount_minor,
        "high_value_threshold_minor": PARAMS.high_value_threshold.amount_minor,
    }
    values.update(overrides)
    return DispositionInputs(**values)  # type: ignore[arg-type]


# key -> (inputs, expected route, rule, review reasons, sign-off reasons). Keys match sample.ts.
CASES = {
    "clean": (inputs("home_kitchen"), "restock", "R13", [], []),
    "missing_cable": (
        inputs(
            "electronics",
            completeness_status="incomplete",
            essential_missing=(MissingPart("usb_cable", True),),
            listing_blockers=(
                "essential_component_missing",
                "functional_test_required",
            ),
        ),
        "refurbish",
        "R09",
        [],
        [],
    ),
    "identity_uncertain": (
        inputs("electronics", identity="uncertain", cosmetic_grade=None),
        None,
        "R03b",
        ["identity_unverified"],
        [],
    ),
    "used_good": (
        inputs("home_kitchen", cosmetic_grade="used_good"),
        "liquidate",
        "R14",
        [],
        [],
    ),
    "lid_not_visible": (
        inputs(
            "home_kitchen",
            completeness_status="uncertain",
            essential_uncertain=(MissingPart("lid", True),),
        ),
        "liquidate",
        "R10",
        ["essential_component_uncertain"],
        [],
    ),
    "damaged_low_value": (
        inputs(
            "home_kitchen",
            cosmetic_grade=None,
            listing_blockers=("damaged_difficult_to_use",),
            max_severity="severe",
            list_price_minor=19900,
        ),
        "dispose",
        "R10",
        [],
        ["S01_dispose_always"],
    ),
    "high_value_electronics": (
        inputs(
            "electronics",
            listing_blockers=("functional_test_required",),
            list_price_minor=999900,
        ),
        "refurbish",
        "R11",
        [],
        ["S02_high_value"],
    ),
}


def main() -> int:
    failures = 0
    for key, (inp, route, rule, review, signoff) in CASES.items():
        d = decide(inp, RULES_VERSION)
        got = (
            d.recommended_disposition,
            d.rule_id,
            list(d.review_reasons),
            list(d.signoff_reasons),
        )
        want = (route, rule, review, signoff)
        ok = got == want
        failures += not ok
        print(
            f"{'ok  ' if ok else 'FAIL'} {key}: {got}"
            + ("" if ok else f" (page shows {want})")
        )
    print(f"rules_version {RULES_VERSION}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
