from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from returns_manager.canonical.hashing import sha256_hex
from returns_manager.canonical.jcs import canonical_bytes
from returns_manager.contract.models import AGENT_NAME, INTEGRITY_CLAIM, SCHEMA_VERSION


def _make_minimal_document(*, decision: str = "REFURBISH", status: str = "finalized") -> dict[str, Any]:
    """Build a minimal valid evidence record document for example generation."""
    checks = [
        {
            "check_key": "identity",
            "verdict": "PASS",
            "confidence_bp": 9300,
            "detail": "Product body features match the catalogue card.",
            "model_version": "gemini-3.8-flash@judgment-v1.0.0",
            "latency_ms": 12000,
        },
        {
            "check_key": "completeness",
            "verdict": "FAIL",
            "confidence_bp": 10000,
            "detail": "USB cable missing (1 of 1 expected).",
            "model_version": "gemini-3.8-flash@judgment-v1.0.0",
            "latency_ms": 12000,
        },
        {
            "check_key": "condition_grade",
            "verdict": "UNCERTAIN",
            "confidence_bp": 5000,
            "detail": "Condition grade could not be reliably determined from the photos.",
            "model_version": "gemini-3.8-flash@judgment-v1.0.0",
            "latency_ms": 12000,
        },
        {
            "check_key": "photo_quality",
            "verdict": "PASS",
            "confidence_bp": 10000,
            "detail": "2 usable photos received.",
            "model_version": "deterministic@quality-gate-1.0.0",
            "latency_ms": 5,
        },
        {
            "check_key": "unit_presence",
            "verdict": "PASS",
            "confidence_bp": 10000,
            "detail": "Product is present in the packaging.",
            "model_version": "gemini-3.8-flash@judgment-v1.0.0",
            "latency_ms": 12000,
        },
        {
            "check_key": "relistable_as_is",
            "verdict": "FAIL",
            "confidence_bp": 10000,
            "detail": "Listing blockers: essential_component_missing, functional_test_required.",
            "model_version": "deterministic@disposition-3f9a1c2b",
            "latency_ms": 1,
        },
        {
            "check_key": "category_policy",
            "verdict": "PASS",
            "confidence_bp": 10000,
            "detail": "Category policy allows the recommended route.",
            "model_version": "deterministic@disposition-3f9a1c2b",
            "latency_ms": 1,
        },
    ]

    doc_without_hash: dict[str, Any] = {
        "record_id": "RTN-0014",
        "schema_version": SCHEMA_VERSION,
        "organization_id": "org_demo_alpha",
        "client_id": "org_demo_alpha",
        "agent": AGENT_NAME,
        "subject": {
            "unit_id": "UNIT-0014",
            "return_id": "01JRETURN14",
            "order_id": "ORD-DUMMY-50014",
            "sku": "SKU-LAMP-LED",
            "asin": "B0DUMMY357",
        },
        "captured_at": "2026-07-18T07:36:00Z",
        "operator_label": "op_eli",
        "images": [
            {
                "image_id": "01JPHOTO001",
                "slot": 1,
                "role": "front",
                "sha256": "a" * 64,
                "quality": "pass",
                "url": None,
            }
        ],
        "checks": checks,
        "outcome": {
            "decision": decision,
            "decided_by": "rules_engine@disposition-3f9a1c2b",
            "decided_at": "2026-07-18T07:37:12Z",
        },
        "overrides": [],
        "status": status,
        "extensions": {
            "returns": {
                "contract_version": "1.0.0",
                "record_id": "RTN-0014",
                "record_version": 1,
                "org_id": "org_demo_alpha",
                "unit_id": "UNIT-0014",
                "return_id": "01JRETURN14",
                "order_id": "ORD-DUMMY-50014",
                "ordered_sku": "SKU-LAMP-LED",
                "ordered_asin": "B0DUMMY357",
                "captured_at": "2026-07-18T07:36:00Z",
                "finalized_at": "2026-07-18T07:37:12Z",
                "comparison_mode": "catalogue_return",
                "integrity": {
                    "document_sha256": "placeholder",
                    "head_event_hash": "a" * 64,
                    "event_count": 5,
                    "ledger_seq": 1,
                    "ledger_hash": "b" * 64,
                    "claim": INTEGRITY_CLAIM,
                },
                "disposition": {
                    "recommended_disposition": "refurbish",
                    "no_recommendation_reason": None,
                    "provisional": False,
                    "assumptions": [],
                    "requires_review": False,
                    "review_reasons": [],
                    "final_disposition": "refurbish",
                    "listing_condition": "Used - Good",
                    "relistable_as_is": False,
                    "rule_id": "R09",
                    "rules_version": "disposition-3f9a1c2b",
                    "decided_by": "deterministic_engine",
                    "requires_signoff": False,
                    "signoff": None,
                    "expected_recovery": None,
                },
                "identity": {
                    "identity_match": "yes",
                    "evidence_strength": "strong",
                    "risk_flags": [],
                    "reasons": [],
                    "observed_identifiers": ["barcode_match"],
                    "feature_checks": [],
                    "evidence": [],
                },
                "completeness": {
                    "status": "incomplete",
                    "parts_list": "usb cable",
                    "parts_missing": "usb cable",
                    "parts_uncertain": "",
                    "components": [],
                },
                "condition": {
                    "amazon_condition": "Used - Good",
                    "cosmetic_grade": "used_good",
                    "listing_blockers": ["essential_component_missing", "functional_test_required"],
                    "functional_check": "not_performed",
                    "packaging_state": "opened",
                    "signs_of_use": "light",
                    "observations": [],
                    "rubric": None,
                },
                "claim_signals": {
                    "item_not_returned": False,
                    "wrong_item_returned": False,
                    "returned_damaged": {"value": False, "basis": [], "evidence": []},
                    "parts_missing": ["usb cable"],
                    "parts_uncertain": [],
                },
                "links": {
                    "self": "/api/v1/units/UNIT-0014/return-evidence",
                    "chain": "/api/v1/units/UNIT-0014/chain",
                    "verification": "/api/v1/units/UNIT-0014/chain/verification",
                    "explain": "/api/v1/units/UNIT-0014/explain",
                },
            }
        },
    }
    doc_without_hash = {k: v for k, v in doc_without_hash.items() if k != "content_hash"}
    doc_without_hash["content_hash"] = "sha256:" + sha256_hex(canonical_bytes(doc_without_hash))
    return doc_without_hash


base = Path(__file__).resolve().parents[1] / "contract" / "examples"
base.mkdir(parents=True, exist_ok=True)

scenarios = [
    (
        "rtn-example-001-refurbish",
        "REFURBISH",
        "finalized",
        "UNIT-EXAMPLE-001",
        "ORD-DEMO-50001",
        "SKU-BT-HEADPHONES",
        "B0DEMO1234",
        "usb charging cable",
    ),
    (
        "rtn-example-002-correct-product",
        "RESTOCK",
        "finalized",
        "UNIT-EXAMPLE-002",
        "ORD-DEMO-50002",
        "SKU-LAMP-LED",
        "B0DEMO2345",
        None,
    ),
    (
        "rtn-example-003-wrong-product",
        "PENDING_REVIEW",
        "awaiting_review",
        "UNIT-EXAMPLE-003",
        "ORD-DEMO-50003",
        "SKU-CHARGER-USB",
        "B0DEMO3456",
        "different item",
    ),
    (
        "rtn-example-004-missing-accessory",
        "REFURBISH",
        "finalized",
        "UNIT-EXAMPLE-004",
        "ORD-DEMO-50004",
        "SKU-HEADSET-BT",
        "B0DEMO4567",
        "left ear cup",
    ),
    (
        "rtn-example-005-missing-multiple",
        "REFURBISH",
        "finalized",
        "UNIT-EXAMPLE-005",
        "ORD-DEMO-50005",
        "SKU-GAMEPAD",
        "B0DEMO5678",
        "usb cable; battery cover",
    ),
    (
        "rtn-example-006-new-looking",
        "RESTOCK",
        "finalized",
        "UNIT-EXAMPLE-006",
        "ORD-DEMO-50006",
        "SKU-SPEAKER",
        "B0DEMO6789",
        None,
    ),
    (
        "rtn-example-007-lightly-used",
        "RESTOCK",
        "finalized",
        "UNIT-EXAMPLE-007",
        "ORD-DEMO-50007",
        "SKU-MOUSE",
        "B0DEMO7890",
        None,
    ),
    (
        "rtn-example-008-damaged",
        "REFURBISH",
        "finalized",
        "UNIT-EXAMPLE-008",
        "ORD-DEMO-50008",
        "SKU-KB-KEYBOARD",
        "B0DEMO8901",
        "screen bezel crack",
    ),
    (
        "rtn-example-009-heavily-damaged",
        "PENDING_REVIEW",
        "awaiting_review",
        "UNIT-EXAMPLE-009",
        "ORD-DEMO-50009",
        "SKU-CAMERA",
        "B0DEMO9012",
        "lens housing damaged",
    ),
    (
        "rtn-example-010-ambiguous-condition",
        "PENDING_REVIEW",
        "awaiting_review",
        "UNIT-EXAMPLE-010",
        "ORD-DEMO-50010",
        "SKU-DRONE",
        "B0DEMO0123",
        "condition unclear",
    ),
    (
        "rtn-example-011-similar-product",
        "PENDING_REVIEW",
        "awaiting_review",
        "UNIT-EXAMPLE-011",
        "ORD-DEMO-50011",
        "SKU-MONITOR",
        "B0DEMO1122",
        "same model but different serial",
    ),
    (
        "rtn-example-012-box-swap",
        "PENDING_REVIEW",
        "awaiting_review",
        "UNIT-EXAMPLE-012",
        "ORD-DEMO-50012",
        "SKU-ROUTER",
        "B0DEMO2233",
        "box mismatch",
    ),
    (
        "rtn-example-013-uncountable-component-opened",
        "REFURBISH",
        "finalized",
        "UNIT-EXAMPLE-013",
        "ORD-DEMO-50013",
        "SKU-TOY",
        "B0DEMO3344",
        "small screws missing",
    ),
    (
        "rtn-example-014-unknown-sku",
        "PENDING_REVIEW",
        "awaiting_review",
        "UNIT-EXAMPLE-014",
        "ORD-DEMO-50014",
        "SKU-UNKNOWN-1",
        "B0DEMO4455",
        "unknown accessory set",
    ),
]

for idx, (filename, decision, status, unit_id, order_id, sku, asin, missing) in enumerate(scenarios, start=1):
    record_id = f"RTN-EXAMPLE-{idx:03d}"
    doc = _make_minimal_document(decision=decision, status=status)
    doc["record_id"] = record_id
    doc["subject"] = {
        "unit_id": unit_id,
        "return_id": f"01JRETURN_{idx:03d}",
        "order_id": order_id,
        "sku": sku,
        "asin": asin,
    }
    doc["captured_at"] = f"2026-07-{(idx % 28) + 1:02d}T07:36:00Z"
    doc["operator_label"] = f"op_demo_{idx}"
    doc["images"][0]["image_id"] = f"01JPHOTO{idx:03d}"
    doc["outcome"]["decision"] = decision
    doc["outcome"]["decided_by"] = (
        "rules_engine@disposition-3f9a1c2b" if decision != "PENDING_REVIEW" else "reviewer:rev_demo"
    )
    doc["outcome"]["decided_at"] = f"2026-07-{(idx % 28) + 1:02d}T07:37:45Z"

    ext = doc["extensions"]["returns"]
    ext["record_id"] = record_id
    ext["unit_id"] = unit_id
    ext["return_id"] = doc["subject"]["return_id"]
    ext["order_id"] = order_id
    ext["ordered_sku"] = sku
    ext["ordered_asin"] = asin
    ext["captured_at"] = doc["captured_at"]
    ext["finalized_at"] = doc["outcome"]["decided_at"]
    ext["identity"]["identity_match"] = "yes" if decision != "PENDING_REVIEW" else "uncertain"
    ext["identity"]["reasons"] = (
        ["barcode_match"] if decision != "PENDING_REVIEW" else ["barcode_match", "manual_review"]
    )
    ext["identity"]["observed_identifiers"] = [asin] if decision != "PENDING_REVIEW" else [asin, "UNKNOWN"]
    ext["completeness"]["status"] = "incomplete" if decision in {"REFURBISH", "RESTOCK"} else "uncertain"
    ext["completeness"]["parts_list"] = "usb charging cable" if missing else "none listed"
    ext["completeness"]["parts_missing"] = missing if missing else ""
    ext["completeness"]["parts_uncertain"] = "" if missing else "condition unclear"
    ext["disposition"]["recommended_disposition"] = (
        decision.lower().replace("_", "") if decision != "PENDING_REVIEW" else "review"
    )
    ext["disposition"]["final_disposition"] = (
        decision.lower().replace("_", "") if decision != "PENDING_REVIEW" else "review"
    )
    ext["disposition"]["requires_review"] = decision == "PENDING_REVIEW"
    ext["disposition"]["review_reasons"] = ["identity_conflict"] if decision == "PENDING_REVIEW" else []
    ext["condition"]["amazon_condition"] = (
        "Used - Good" if decision in {"RESTOCK", "REFURBISH"} else "Uncertain"
    )
    ext["condition"]["listing_blockers"] = (
        ["essential_component_missing"] if decision in {"RESTOCK", "REFURBISH"} else []
    )
    ext["claim_signals"]["wrong_item_returned"] = decision == "PENDING_REVIEW"
    ext["claim_signals"]["parts_missing"] = (
        ["usb charging cable"] if decision in {"REFURBISH", "RESTOCK"} and missing else []
    )
    ext["claim_signals"]["parts_uncertain"] = ["condition unclear"] if decision == "PENDING_REVIEW" else []
    ext["claim_signals"]["returned_damaged"] = {"value": False}

    for check in doc["checks"]:
        key = check["check_key"]
        if key == "identity":
            check["verdict"] = "PASS" if decision != "PENDING_REVIEW" else "UNCERTAIN"
        elif key == "completeness":
            check["verdict"] = "FAIL" if decision in {"REFURBISH", "RESTOCK"} else "UNCERTAIN"
        elif key == "condition_grade":
            check["verdict"] = "PASS" if decision in {"RESTOCK", "REFURBISH"} else "UNCERTAIN"
        elif key == "relistable_as_is":
            check["verdict"] = "FAIL" if decision in {"REFURBISH", "RESTOCK"} else "UNCERTAIN"
        elif key in {"category_policy", "photo_quality", "unit_presence"}:
            check["verdict"] = "PASS"

    doc_without_hash = {k: v for k, v in doc.items() if k != "content_hash"}
    doc["content_hash"] = "sha256:" + sha256_hex(canonical_bytes(doc_without_hash))
    path = base / f"{filename}.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(path.name)
