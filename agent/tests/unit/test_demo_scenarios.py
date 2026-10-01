"""The 10-row demo input (`manual_test_images/returns_input_10_demo.csv`) end to end through the real batch
code: CSV split, synthesized card, rubric, policy, consistency rules, identity fusion, completeness,
condition, rules engine, auto-approve and the output row. Only two things are stood in for:

- the photo download (a tiny PNG; the model never sees it here), and
- the Gemini session, replaced by the judgment a careful inspector reports for each row's real photos.

The crafted judgments describe what the photos show (checked by eye against the Wikimedia images), not
the `scenario` column, which the code never reads. They pin the deterministic behaviour; whether the live
model reports the same observations is checked by a live run, not here.

Where the photos contradict the demo's planned label (`scratch/create_10_demo.py`), the photos win:
006 and 014 show no wear (planned: liquidate), and 031's return photo is a DualSense Edge, a different
product from the DualSense sold (planned: restock).
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from PIL import Image

from returns_manager.api.routes.batch import _split_combined_csv
from returns_manager.batch import runner
from returns_manager.batch.cards import DEFAULT_LIST_PRICE_MINOR
from returns_manager.batch.io_csv import parse_before_csv, parse_returned_csv
from returns_manager.batch.parts import parse_parts_list
from returns_manager.config import get_settings
from returns_manager.judgment.pipeline import SINGLE_PHOTO_NOTE
from returns_manager.llm.schemas import JudgmentV1

DEMO = Path(__file__).resolve().parents[2] / "manual_test_images" / "returns_input_10_demo.csv"
NO_WEAR = "There are absolutely no signs of wear"
SOME_WEAR = "may show some signs of wear"


def _judgment(
    parts_list: str,
    *,
    identity: str,
    features: tuple[str, str],
    confidence: float,
    risk_flags: tuple[str, ...] = (),
    identity_reason: str | None = None,
    grade: str | None = "used_like_new",
    phrase: str | None = NO_WEAR,
    grade_reason: str | None = None,
    signs_of_use: str = "none_visible",
    cleanliness: str = "clean",
    observed_state: str = "opened_unused",
    issues: tuple[str, ...] = ("none",),
    defects: tuple[dict[str, Any], ...] = (),
) -> JudgmentV1:
    """One single-photo judgment: the main unit is in view, the loose accessories are out of frame."""
    parts = parse_parts_list(parts_list)
    components = [
        {
            "component_id": p.component_id,
            "observed_quantity": 1 if i == 0 else None,
            "visibility": "observed_present" if i == 0 else "not_visible",
            "status": "present" if i == 0 else "uncertain",
            "photos": ["P1"] if i == 0 else [],
            "confidence": 0.9 if i == 0 else 0.0,
        }
        for i, p in enumerate(parts)
    ]
    return JudgmentV1.model_validate(
        {
            "schema_version": "judgment/v1",
            "photo_reports": [
                {
                    "photo": "P1",
                    "usable": True,
                    "views": ["front"],
                    "visible_regions": ["product_body"],
                    "issues": list(issues),
                }
            ],
            "unit_presence": {
                "status": "product_present",
                "evidence": [{"photo": "P1", "box_2d": None, "observation": "Product in view."}],
            },
            "identity": {
                "identity_match": identity,
                "observed_identifiers": [],
                "feature_checks": [
                    {"feature_id": "df_catalog_appearance", "result": features[0], "photo": "P1"},
                    {
                        "feature_id": "df_catalog_markings",
                        "result": features[1],
                        "photo": None if features[1] == "not_visible" else "P1",
                    },
                ],
                "risk_flags": list(risk_flags),
                "likely_actual_sku": None,
                "uncertainty_reason": identity_reason,
                "confidence": confidence,
                "evidence": [{"photo": "P1", "box_2d": None, "observation": "Product body compared."}],
            },
            "completeness": {
                "components": components,
                "unexpected_items": [],
                "uncertainty_reason": "component_area_not_visible" if len(parts) > 1 else None,
            },
            "condition": {
                "packaging_state": "not_visible",
                "observations": list(defects),
                "signs_of_use": signs_of_use,
                "cleanliness": cleanliness,
                "outer_shipping_damage_observed": None,
                "functional_check": "not_performed",
                "proposed_grade": {
                    "grade_code": grade,
                    "rubric_phrases_matched": [phrase] if phrase else [],
                    "uncertainty_reason": grade_reason,
                    "confidence": 0.8 if grade else 0.0,
                },
            },
            "model_observed_state": observed_state,
            "retake_requests": [],
            "uncertainties": [],
            "untrusted_text_observed": [],
        }
    )


# record_id -> what the return photo shows, as a judgment (None: the row has no return photo).
JUDGMENTS: dict[str, Any] = {
    # Four iPhones side by side; one is labelled iPhone 15 but the returned unit cannot be singled out.
    "RTN-C26RM-001": lambda parts: _judgment(
        parts,
        identity="uncertain",
        features=("match", "not_visible"),
        confidence=0.5,
        identity_reason="similar_product",
    ),
    # Sold iPhone 15 Pro (triple camera); the return photo is an iPhone 15 / 15 Plus store display.
    "RTN-C26RM-002": lambda parts: _judgment(
        parts,
        identity="no",
        features=("mismatch", "mismatch"),
        confidence=0.85,
        risk_flags=("model_mismatch",),
        observed_state="uncertain",  # what the live model reported for this row
    ),
    # Pixel 8 front: rose frame and punch-hole match; no visible wear.
    "RTN-C26RM-006": lambda parts: _judgment(
        parts, identity="yes", features=("match", "not_visible"), confidence=0.8
    ),
    "RTN-C26RM-008": None,
    # MacBook Pro 16 in a very dark room: the model is identifiable, the condition is not.
    "RTN-C26RM-013": lambda parts: _judgment(
        parts,
        identity="yes",
        features=("match", "not_visible"),
        confidence=0.75,
        grade=None,
        phrase=None,
        grade_reason="bad_photo",
        signs_of_use="not_determinable",
        cleanliness="not_determinable",
        observed_state="uncertain",
        issues=("too_dark",),
    ),
    # Dell XPS 13 underside: "XPS" lettering matches; clean, one regulatory label corner slightly lifted.
    "RTN-C26RM-014": lambda parts: _judgment(
        parts,
        identity="yes",
        features=("match", "match"),
        confidence=0.9,
        grade="used_very_good",
        phrase=SOME_WEAR,
        signs_of_use="light",
        defects=(
            {
                "defect_type": "label_damage",
                "severity": "minor",
                "location_note": "corner of the bottom regulatory label lifted",
                "photo": "P1",
                "box_2d": None,
                "confidence": 0.7,
            },
        ),
    ),
    "RTN-C26RM-028": None,
    # Sold DualSense; the return photo is a DualSense Edge (black patterned touchpad, Fn buttons).
    "RTN-C26RM-031": lambda parts: _judgment(
        parts,
        identity="no",
        features=("mismatch", "not_visible"),
        confidence=0.8,
        risk_flags=("variant_mismatch",),
        observed_state="uncertain",
    ),
    # MX Master 3S underside: Logitech markings and shape match; clean.
    "RTN-C26RM-041": lambda parts: _judgment(
        parts, identity="yes", features=("match", "match"), confidence=0.85
    ),
    # Sold a Logitech K380 keyboard; the return photo is a Razer DeathAdder mouse.
    "RTN-C26RM-042": lambda parts: _judgment(
        parts,
        identity="no",
        features=("mismatch", "mismatch"),
        confidence=0.95,
        risk_flags=("brand_mismatch", "model_mismatch"),
    ),
}

# record_id -> expected output columns (my answer key, written from the photos before the run).
EXPECTED: dict[str, dict[str, str]] = {
    "RTN-C26RM-001": {
        "photo_identity_match": "uncertain",
        "agent_disposition": "restock",
        "auto_disapproved": "false",
    },
    "RTN-C26RM-002": {
        "photo_identity_match": "no",
        "agent_disposition": "dispose",
        "auto_disapproved": "true",
    },
    "RTN-C26RM-006": {
        "photo_identity_match": "yes",
        "agent_disposition": "restock",
        "auto_disapproved": "false",
        "amazon_condition": "Used - Like New",
    },
    "RTN-C26RM-008": {"failure_reason": "no_return_photo", "agent_disposition": ""},
    "RTN-C26RM-013": {
        "photo_identity_match": "yes",
        "agent_disposition": "refurbish",
        "auto_disapproved": "false",
        "amazon_condition": "uncertain",
    },
    "RTN-C26RM-014": {
        "photo_identity_match": "yes",
        "agent_disposition": "restock",
        "auto_disapproved": "false",
        "amazon_condition": "Used - Very Good",
    },
    "RTN-C26RM-028": {"failure_reason": "no_return_photo", "agent_disposition": ""},
    "RTN-C26RM-031": {
        "photo_identity_match": "no",
        "agent_disposition": "dispose",
        "auto_disapproved": "true",
    },
    "RTN-C26RM-041": {
        "photo_identity_match": "yes",
        "agent_disposition": "restock",
        "auto_disapproved": "false",
        "amazon_condition": "Used - Like New",
    },
    "RTN-C26RM-042": {
        "photo_identity_match": "no",
        "agent_disposition": "dispose",
        "auto_disapproved": "true",
    },
}


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 130, 140)).save(buf, format="PNG")
    return buf.getvalue()


async def _run_demo(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    before_bytes, returned_bytes = _split_combined_csv(DEMO.read_bytes(), DEMO.name)
    before = parse_before_csv(before_bytes.decode("utf-8"), "before.csv")
    returned = parse_returned_csv(returned_bytes.decode("utf-8"), "returned.csv")
    png = _png()
    results: dict[str, Any] = {}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=png))
    ) as http:
        for row in returned:
            make = JUDGMENTS[row.record_id]
            parts = before[row.unit_id].parts_list

            async def fake_session(*_a: Any, _make: Any = make, _parts: str = parts, **_k: Any) -> Any:
                assert _make is not None, "a row without a return photo must never reach the model"
                return SimpleNamespace(judgment=_make(_parts))

            monkeypatch.setattr(runner, "_run_judgment_with_fallback", fake_session)
            results[row.record_id] = await runner.process_returned_row(
                row,
                before,
                settings=get_settings(),
                client=None,  # type: ignore[arg-type]
                http_client=http,
                quota=runner._NoDbQuota(rpm=6000),
                default_category=None,
                list_price_minor=DEFAULT_LIST_PRICE_MINOR,
            )
    return results


async def test_demo_rows_match_the_answer_key(monkeypatch: pytest.MonkeyPatch) -> None:
    results = await _run_demo(monkeypatch)
    assert set(results) == set(EXPECTED)
    mismatches = []
    for record_id, expected in EXPECTED.items():
        out = results[record_id].output_row
        for column, value in expected.items():
            if out[column] != value:
                mismatches.append(f"{record_id}.{column}: expected {value!r}, got {out[column]!r}")
    assert not mismatches, "\n" + "\n".join(mismatches)


async def test_demo_rows_are_never_auto_approved_and_always_go_to_a_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every demo row needs a person: single photos, accessories out of frame, or a wrong item."""
    results = await _run_demo(monkeypatch)
    for record_id, res in results.items():
        out = res.output_row
        assert out["auto_approved"] == "false", record_id
        assert out["operator_disposition"] == "pending_review", record_id


async def test_demo_wrong_items_dispose_only_with_signoff_and_say_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = await _run_demo(monkeypatch)
    for record_id in ("RTN-C26RM-002", "RTN-C26RM-031", "RTN-C26RM-042"):
        res = results[record_id]
        assert res.detail["decision"]["rule_id"] == "R03", record_id
        assert "S01_dispose_always" in res.detail["decision"]["signoff_reasons"], record_id
        assert res.output_row["rationale"].startswith("Wrong item returned"), record_id


async def test_demo_photo_rows_state_single_photo_calibration_and_no_part_is_called_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = await _run_demo(monkeypatch)
    for record_id, res in results.items():
        out = res.output_row
        if out["failure_reason"]:
            assert res.detail is None, record_id  # fail-open rows carry no invented detail
            assert out["requires_review"] == "true", record_id
            assert out["rationale"].startswith("No return photo was supplied"), record_id
            continue
        assert SINGLE_PHOTO_NOTE in out["rationale"], record_id
        assert out["parts_missing"] == "", record_id  # out-of-frame accessories are not "missing"
        assert out["requires_review"] == "true", record_id
        model_checks = [c for c in res.detail["checks"] if c["source"] == "model"]
        assert all(c["confidence_bp"] <= 8500 for c in model_checks), record_id  # -15% calibration
