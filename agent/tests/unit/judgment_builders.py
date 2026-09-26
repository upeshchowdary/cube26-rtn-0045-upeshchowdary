"""Crafted judgment/v1 outputs and contexts for scenario and table tests (§19: no model involved).

Contexts use the real reference files (rubrics, policies, params) and either a real product card or a card
built here. `judgment(...)` starts from a clean "opened, complete, like-new, identity proven on the product
body" output; tests change only what the scenario is about.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from returns_manager.config import REPO_ROOT
from returns_manager.judgment.pipeline import PhotoGate, PipelineResult, run_pipeline
from returns_manager.judgment.types import BarcodeDecode, EffectivePolicy, JudgmentContext
from returns_manager.llm.schemas import JudgmentV1
from returns_manager.reference.models import (
    CategoryPolicyV1,
    ConditionRubricV1,
    DispositionParamsV1,
    ProductCardV1,
)

REF = REPO_ROOT / "reference"
RULES_VERSION = "disposition-test"


def _load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def card(org: str, sku: str) -> ProductCardV1:
    return ProductCardV1.model_validate(_load(REF / "products" / org / f"{sku}.yaml"))


def rubric(category: str) -> ConditionRubricV1:
    return ConditionRubricV1.model_validate(_load(REF / "rubrics" / "amazon.co.uk" / f"{category}.yaml"))


def policy(category: str, overrides: dict[str, object] | None = None) -> EffectivePolicy:
    p = CategoryPolicyV1.model_validate(_load(REF / "policies" / "amazon.co.uk" / f"{category}.yaml"))
    return EffectivePolicy.from_policy(p, overrides)


def params() -> DispositionParamsV1:
    return DispositionParamsV1.model_validate(_load(REF / "rules" / "disposition-params.yaml"))


def headphones_card(price_minor: int = 399900) -> ProductCardV1:
    """The problem statement's example product (Appendix A): headphones, carrying case, USB cable, manual."""
    src = {"type": "test_fixture", "ref": "problem statement example"}
    return ProductCardV1.model_validate(
        {
            "schema": "product-card/v1",
            "version": "1.0.0",
            "org_id": "org_demo_alpha",
            "sku": "SKU-HEADPHONES-TEST",
            "identifiers": {"asin": None, "barcode_values": ["X00HEADPHONES"]},
            "title": "Wireless headphones",
            "brand": "TestBrand",
            "category_key": "electronics",
            "distinguishing_features": [
                {
                    "id": "df_cup_logo",
                    "description": "Logo on the ear cup",
                    "location": "product_body",
                    "importance": "critical",
                },
                {
                    "id": "df_headband",
                    "description": "Grey fabric headband",
                    "location": "product_body",
                    "importance": "critical",
                },
            ],
            "similar_skus": [{"sku": "SKU-HEADPHONES-LITE", "differs_by": ["no fabric headband"]}],
            "components": [
                {
                    "id": "headphones",
                    "name": "headphones",
                    "quantity": 1,
                    "essential": True,
                    "replaceable": False,
                    "visual_cues": "headset",
                    "source": src,
                },
                {
                    "id": "carrying_case",
                    "name": "carrying case",
                    "quantity": 1,
                    "essential": True,
                    "replaceable": True,
                    "visual_cues": "zip case",
                    "source": src,
                },
                {
                    "id": "usb_cable",
                    "name": "usb cable",
                    "quantity": 1,
                    "essential": True,
                    "replaceable": True,
                    "visual_cues": "USB-C cable",
                    "source": src,
                },
                {
                    "id": "manual",
                    "name": "manual",
                    "quantity": 1,
                    "essential": False,
                    "replaceable": True,
                    "visual_cues": "leaflet",
                    "source": src,
                },
            ],
            "reference_images": [],
            "value": {
                "synthetic": True,
                "list_price": {"amount_minor": price_minor, "currency": "INR"},
                "recovery_rate_bp": {
                    "restock_new": 10000,
                    "restock_used": 6500,
                    "refurbish": 5500,
                    "liquidate": 2000,
                    "dispose": 0,
                },
                "refurbish_cost": {"amount_minor": 30000, "currency": "INR"},
            },
        }
    )


def context(
    product: ProductCardV1,
    *,
    category: str | None = None,
    other_cards: dict[str, ProductCardV1] | None = None,
    barcodes: tuple[BarcodeDecode, ...] = (),
    policy_overrides: dict[str, object] | None = None,
    photos: tuple[str, ...] = ("P1", "P2", "P3"),
) -> JudgmentContext:
    cat = category or product.category_key
    rub = rubric(cat)
    text = "\n".join([g.text for g in rub.grades] + [u.text for u in rub.unacceptable_conditions])
    return JudgmentContext(
        org_id=product.org_id,
        ordered_sku=product.sku,
        card=product,
        other_cards=other_cards or {},
        rubric=rub,
        policy=policy(cat, policy_overrides),
        params=params(),
        photo_aliases=photos,
        reference_aliases=("R1",),
        barcodes=barcodes,
        rubric_text_sent=text,
    )


def labelled(product: ProductCardV1, code: str = "X00TESTLABEL", **kwargs: Any) -> JudgmentContext:
    """Context in which the unit's barcode label decodes to the ordered SKU (as an FBA unit's label would).

    Needed for cards with fewer than two critical product-body features: without a matching barcode, identity
    `yes` requires two such matches (§11.9 row 7).
    """
    ids = product.identifiers.model_copy(update={"barcode_values": [code]})
    return context(
        product.model_copy(update={"identifiers": ids}),
        barcodes=(BarcodeDecode("P1", code, "Code128"),),
        **kwargs,
    )


def judgment(ctx: JudgmentContext, **changes: Any) -> JudgmentV1:
    """Return a clean judgment with dotted-path changes, such as identity.identity_match=no."""
    c = ctx.card
    body_features = [
        f for f in c.distinguishing_features if f.location == "product_body" and f.importance == "critical"
    ]
    grade_text = next(
        g.text
        for g in ctx.rubric.grades
        if g.code == ("used_like_new" if len(ctx.rubric.grades) > 1 else "new")
    )
    base: dict[str, Any] = {
        "schema_version": "judgment/v1",
        "photo_reports": [
            {
                "photo": p,
                "usable": True,
                "views": ["front"],
                "visible_regions": ["product_body", "accessory_area", "interior_of_packaging"],
                "issues": ["none"],
            }
            for p in ctx.photo_aliases
        ],
        "unit_presence": {
            "status": "product_present",
            "evidence": [{"photo": "P1", "box_2d": None, "observation": "product in box"}],
        },
        "identity": {
            "identity_match": "yes",
            "observed_identifiers": [],
            "feature_checks": [{"feature_id": f.id, "result": "match", "photo": "P1"} for f in body_features],
            "risk_flags": [],
            "likely_actual_sku": None,
            "uncertainty_reason": None,
            "confidence": 0.9,
            "evidence": [
                {"photo": "P1", "box_2d": [100, 100, 600, 600], "observation": "features match the card"}
            ],
        },
        "completeness": {
            "components": [
                {
                    "component_id": comp.id,
                    "observed_quantity": comp.quantity,
                    "visibility": "observed_present",
                    "status": "present",
                    "photos": ["P2"],
                    "confidence": 0.9,
                }
                for comp in c.components
            ],
            "unexpected_items": [],
            "uncertainty_reason": None,
        },
        "condition": {
            "packaging_state": "opened_packaging_intact",
            "observations": [],
            "signs_of_use": "none_visible",
            "cleanliness": "clean",
            "outer_shipping_damage_observed": False,
            "functional_check": "not_performed",
            "proposed_grade": {
                "grade_code": "used_like_new" if len(ctx.rubric.grades) > 1 else None,
                "rubric_phrases_matched": [grade_text[:40]],
                "uncertainty_reason": None if len(ctx.rubric.grades) > 1 else "condition_ambiguous",
                "confidence": 0.8,
            },
        },
        "model_observed_state": "opened_unused",
        "retake_requests": [],
        "uncertainties": [],
        "untrusted_text_observed": [],
    }
    for path, value in changes.items():
        node: Any = base
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[int(k)] if isinstance(node, list) else node[k]
        last = keys[-1]
        if isinstance(node, list):
            node[int(last)] = copy.deepcopy(value)
        else:
            node[last] = copy.deepcopy(value)
    return JudgmentV1.model_validate(base)


def component(ctx: JudgmentContext, j: JudgmentV1, cid: str, **fields: Any) -> JudgmentV1:
    data = j.model_dump()
    for comp in data["completeness"]["components"]:
        if comp["component_id"] == cid:
            comp.update(fields)
    return JudgmentV1.model_validate(data)


def defect(defect_type: str = "scratch", severity: str = "minor", photo: str = "P1") -> dict[str, Any]:
    return {
        "defect_type": defect_type,
        "severity": severity,
        "location_note": "side",
        "photo": photo,
        "box_2d": None,
        "confidence": 0.8,
    }


def grade(j: JudgmentV1, code: str | None, ctx: JudgmentContext | None = None) -> JudgmentV1:
    data = j.model_dump()
    pg = data["condition"]["proposed_grade"]
    pg["grade_code"] = code
    if ctx is not None and code is not None:
        pg["rubric_phrases_matched"] = [next(g.text for g in ctx.rubric.grades if g.code == code)[:40]]
    pg["uncertainty_reason"] = None if code else "condition_ambiguous"
    return JudgmentV1.model_validate(data)


def run(
    ctx: JudgmentContext,
    j: JudgmentV1,
    *,
    non_fail: int = 3,
    acknowledged: bool = False,
    auto: bool = True,
    operator_state: str | None = None,
    integrity_flags: tuple[str, ...] = (),
) -> PipelineResult:
    return run_pipeline(
        j,
        ctx,
        photo_gate=PhotoGate(non_fail, acknowledged, integrity_flags),
        rules_version=RULES_VERSION,
        auto_disposition_enabled=auto,
        operator_state=operator_state,
    )
