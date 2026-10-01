"""Generate the contract examples in `agent/contract/examples/` from real pipeline runs.

Each example is one official scenario (plus extras) on the catalogued test headphones card: a crafted,
synthetic model judgment goes through the same code as a live inspection (referential validation,
consistency rules, identity fusion, completeness, condition, the rules engine) and then through
`contract.service.build_evidence_record`. Nothing in a record is hand-edited, so every route, rule id,
check and claim signal is what the engine computes for that evidence.

Every record is synthetic: ids say EXAMPLE, the operator label says synthetic, and no photo exists.
`tests/unit/test_contract.py` fails if a committed example drifts from what this script produces.

Run from `agent/`:  uv run python scripts/generate_example_contract_records.py
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from tests.unit import judgment_builders as b  # noqa: E402

from returns_manager.canonical.hashing import sha256_hex  # noqa: E402
from returns_manager.canonical.jcs import canonical_bytes  # noqa: E402
from returns_manager.contract.service import build_evidence_record  # noqa: E402
from returns_manager.disposition.params import load_params, rules_version  # noqa: E402
from returns_manager.judgment.pipeline import PhotoGate, PipelineResult, run_pipeline  # noqa: E402
from returns_manager.judgment.types import JudgmentContext  # noqa: E402
from returns_manager.llm.schemas import JudgmentV1  # noqa: E402

EXAMPLES_DIR = AGENT_DIR / "contract" / "examples"
MODEL_VERSION = "synthetic-example@judgment-v1"
ORG = "org_demo_alpha"


def _edit(j: JudgmentV1, fn: Callable[[dict[str, Any]], None]) -> JudgmentV1:
    data = j.model_dump()
    fn(data)
    return JudgmentV1.model_validate(data)


def _missing(*component_ids: str) -> Callable[[dict[str, Any]], None]:
    def apply(d: dict[str, Any]) -> None:
        for c in d["completeness"]["components"]:
            if c["component_id"] in component_ids:
                c.update(
                    status="missing",
                    visibility="observed_absent_in_clear_view",
                    observed_quantity=0,
                    photos=["P2"],
                )

    return apply


def _defects(*defects: dict[str, Any], grade: str | None) -> Callable[[dict[str, Any]], None]:
    def apply(d: dict[str, Any]) -> None:
        d["condition"]["observations"] = list(defects)
        d["condition"]["signs_of_use"] = "moderate" if defects else "none_visible"
        d["condition"]["proposed_grade"].update(
            grade_code=grade,
            rubric_phrases_matched=[],
            uncertainty_reason=None if grade else "condition_ambiguous",
        )
        d["model_observed_state"] = "damaged" if defects else d["model_observed_state"]

    return apply


def _wrong_item(d: dict[str, Any]) -> None:
    d["identity"].update(identity_match="no", risk_flags=["model_mismatch"], confidence=0.9)
    for fc in d["identity"]["feature_checks"]:
        fc["result"] = "mismatch"


def _similar(d: dict[str, Any]) -> None:
    d["identity"].update(identity_match="uncertain", uncertainty_reason="similar_product", confidence=0.5)
    d["identity"]["feature_checks"][1]["result"] = "not_visible"


def _sealed(d: dict[str, Any]) -> None:
    d["condition"]["packaging_state"] = "factory_sealed_intact"
    d["model_observed_state"] = "factory_sealed"


def _empty_box(d: dict[str, Any]) -> None:
    d["unit_presence"]["status"] = "empty_packaging"
    d["model_observed_state"] = "empty_box"


def _uncountable_card() -> Any:
    card = b.headphones_card()
    comps = [
        c.model_copy(update={"verifiable_by_photo": False}) if c.id == "usb_cable" else c
        for c in card.components
    ]
    return card.model_copy(update={"components": comps})


# (file slug, scenario description, context factory, judgment edit, grade code for the clean judgment)
Scenario = tuple[str, str, Callable[[], JudgmentContext], Callable[[JudgmentV1, JudgmentContext], JudgmentV1]]


def _ctx() -> JudgmentContext:
    return b.context(b.headphones_card())


SCENARIOS: list[Scenario] = [
    (
        "001-refurbish",
        "S01 correct product, opened, used electrical item: needs a functional test",
        _ctx,
        lambda j, c: j,
    ),
    (
        "002-correct-product",
        "S01 correct product, factory sealed",
        _ctx,
        lambda j, c: b.grade(_edit(j, _sealed), "new", c),
    ),
    ("003-wrong-product", "S02 wrong product returned", _ctx, lambda j, c: _edit(j, _wrong_item)),
    (
        "004-missing-accessory",
        "S03 one replaceable accessory missing in clear view",
        _ctx,
        lambda j, c: _edit(j, _missing("usb_cable")),
    ),
    (
        "005-missing-multiple",
        "S04 several accessories missing in clear view",
        _ctx,
        lambda j, c: _edit(j, _missing("usb_cable", "carrying_case")),
    ),
    (
        "006-new-looking",
        "S05 new-looking return, opened box, no wear",
        _ctx,
        lambda j, c: b.grade(j, "used_like_new", c),
    ),
    (
        "007-lightly-used",
        "S06 lightly used: minor cosmetic scratch",
        _ctx,
        lambda j, c: _edit(j, _defects(b.defect("scratch", "minor"), grade="used_very_good")),
    ),
    (
        "008-damaged",
        "S07 damaged: moderate crack on the headband",
        _ctx,
        lambda j, c: _edit(j, _defects(b.defect("crack", "moderate"), grade="used_acceptable")),
    ),
    (
        "009-heavily-damaged",
        "S08 heavily damaged: severe crack and deformation",
        _ctx,
        lambda j, c: _edit(
            j, _defects(b.defect("crack", "severe"), b.defect("deformation", "severe"), grade=None)
        ),
    ),
    (
        "010-ambiguous-condition",
        "S09 ambiguous condition: grade not determinable",
        _ctx,
        lambda j, c: b.grade(j, None),
    ),
    (
        "011-similar-product",
        "S10 a similar-looking product: identity not verified",
        _ctx,
        lambda j, c: _edit(j, _similar),
    ),
    (
        "012-box-swap",
        "X06 box swap: packaging barcode matches, product body does not",
        lambda: b.labelled(b.headphones_card(), code="X00HEADPHONES"),
        lambda j, c: _edit(j, _wrong_item),
    ),
    (
        "013-uncountable-component-opened",
        "X07 a part that photos cannot verify, packaging opened",
        lambda: b.context(_uncountable_card()),
        lambda j, c: j,
    ),
    ("014-empty-box", "X01 empty box: primary unit not present", _ctx, lambda j, c: _edit(j, _empty_box)),
]


def _plain(value: Any) -> Any:
    return json.loads(json.dumps(dataclasses.asdict(value) if dataclasses.is_dataclass(value) else value))


def _checks(r: PipelineResult, rv: str) -> list[dict[str, Any]]:
    return [
        {
            "check_key": c.check_key,
            "verdict": c.verdict,
            "confidence_bp": c.confidence_bp,
            "detail": c.detail,
            "model_version": MODEL_VERSION if c.source == "model" else f"deterministic@{rv}",
            "latency_ms": 0,
        }
        for c in r.checks
    ]


def build_example(index: int, slug: str, description: str, make_ctx: Any, change: Any) -> dict[str, Any]:
    ctx = make_ctx()
    rv = rules_version(load_params())
    r = run_pipeline(change(b.judgment(ctx), ctx), ctx, photo_gate=PhotoGate(3, False), rules_version=rv)
    d = r.decision
    settled = d.recommended_disposition is not None and not r.requires_review and not d.requires_signoff
    captured = datetime(2026, 7, index, 7, 36, tzinfo=UTC)
    record_id = f"RTN-EXAMPLE-{index:03d}"
    ret = {
        "record_id": record_id,
        "unit_id": f"UNIT-EXAMPLE-{index:03d}",
        "return_id": f"RET-EXAMPLE-{index:03d}",
        "order_id": f"ORD-EXAMPLE-{index:03d}",
        "ordered_sku": ctx.card.sku,
        "ordered_asin": "",
        "created_at": captured,
    }
    result = {
        "fused_identity": _plain(r.identity),
        "components": _plain(r.completeness),
        "completeness_status": r.completeness.status,
        "condition": _plain(r.condition),
        "model_observed_state": r.judgment.model_observed_state,
        "disposition": {**_plain(d), "escalation_triggers": list(r.escalation_triggers)},
        "relistable_as_is": r.condition.relistable_as_is,
        "claim_signals": _plain(r.claims),
        "uncertainties": [u.model_dump() for u in r.judgment.uncertainties],
        "checks": _checks(r, rv),
    }
    values = {
        # an operator accepts only a settled route; anything needing review or sign-off stays open
        "disposition": d.recommended_disposition if settled else None,
        "identity_match": r.identity.identity_match,
        "unit_presence": r.presence.status,
        "amazon_condition": r.condition.amazon_condition,
        "cosmetic_grade": r.condition.cosmetic_grade,
        "components": {},
    }
    photos = [
        {
            "photo_id": f"PHOTO-EXAMPLE-{index:03d}-{slot}",
            "slot": slot,
            "role_hint": "other",
            "sha256_original": sha256_hex(f"synthetic example {index} photo {slot}".encode()),
            "quality_status": "pass",
        }
        for slot in (1, 2, 3)
    ]
    doc = build_evidence_record(
        org_id=ORG,
        ret=ret,
        result=result,
        values=values,
        overrides=[],
        photos=photos,
        record_version=1,
        actor_id="synthetic-example (no real operator)",
        decided_by=f"rules_engine@{rv}" if settled else "pending",
    )
    # Fixed timestamps and status so regenerating is reproducible; the content hash is recomputed.
    doc["outcome"]["decided_at"] = captured.isoformat().replace("+00:00", "Z")
    doc["extensions"]["returns"]["finalized_at"] = doc["outcome"]["decided_at"]
    doc["status"] = "finalized" if settled else r.target_status
    doc["extensions"]["returns"]["scenario"] = f"SYNTHETIC EXAMPLE. {description}."
    for image in doc["images"]:
        image.pop("storage_key", None)
    doc.pop("content_hash", None)
    doc["content_hash"] = "sha256:" + sha256_hex(canonical_bytes(doc))
    return doc


def all_examples() -> dict[str, dict[str, Any]]:
    return {
        f"rtn-example-{slug}.json": build_example(i, slug, desc, make_ctx, change)
        for i, (slug, desc, make_ctx, change) in enumerate(SCENARIOS, start=1)
    }


def main() -> None:
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    wanted = all_examples()
    for stale in EXAMPLES_DIR.glob("rtn-example-*.json"):
        if stale.name not in wanted:
            stale.unlink()
    for name, doc in wanted.items():
        (EXAMPLES_DIR / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
        dispo = doc["extensions"]["returns"]["disposition"]
        print(f"{name}: {dispo['rule_id']} -> {dispo['recommended_disposition']} ({doc['status']})")


if __name__ == "__main__":
    main()
