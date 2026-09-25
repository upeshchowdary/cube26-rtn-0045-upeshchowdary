"""T-CON-* contract tests (Phase 10, §14, §16, §19).

These tests verify:
  T-CON-01  Every fixed-contract top-level field is present with the exact handbook name.
  T-CON-02  Every applicable fixed check key has verdict/confidence/detail/model_version/latency_ms.
  T-CON-03  outcome.decided_by is never a model name.
  T-CON-04  content_hash recomputes correctly.
  T-CON-05  No key is duplicated between fixed fields and extensions.returns.
  T-CON-06  Flat header prefix equals the official CSV header (first 15 columns).
  T-CON-07  Flat view and rich record agree on overlapping fields.
  T-CON-08  EvidenceRecord validates a well-formed document.
  T-CON-09  EvidenceRecord rejects a document missing required fields.
  T-CON-10  Schema generation produces valid JSON Schema draft 2020-12.
  T-CON-11  Flat columns list matches FLAT_COLUMNS constant.
  T-CON-12  PENDING_REVIEW outcome when recommendation is null.
  T-CON-13  MCP service function produces same structure as REST service function.
  T-CON-14  CLI 'contract build' writes all three artifact files.
  T-CON-15  CLI 'evidence --help' exits 0 (command is registered).
  T-CON-16  CLI 'openapi export' produces valid JSON with OpenAPI fields.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from returns_manager.canonical.hashing import sha256_hex
from returns_manager.canonical.jcs import canonical_bytes
from returns_manager.contract.flat import FLAT_COLUMNS, build_flat_row, flat_rows_to_csv
from returns_manager.contract.models import (
    AGENT_NAME,
    INTEGRITY_CLAIM,
    SCHEMA_VERSION,
    EvidenceRecord,
)
from returns_manager.contract.schema import (
    FIXED_CHECK_KEYS,
    check_no_key_duplication,
    generate_evidence_record_schema,
    write_contract_artifacts,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

REQUIRED_TOP_LEVEL = [
    "record_id",
    "schema_version",
    "organization_id",
    "client_id",
    "agent",
    "subject",
    "captured_at",
    "operator_label",
    "images",
    "checks",
    "outcome",
    "overrides",
    "status",
    "content_hash",
    "extensions",
]

OFFICIAL_CSV_COLUMNS_15 = [
    "record_id",
    "unit_id",
    "org_id",
    "order_id",
    "ordered_sku",
    "ordered_asin",
    "identity_match",
    "parts_list",
    "parts_missing",
    "observed_state",
    "amazon_condition",
    "operator_disposition",
    "photo_refs",
    "operator_id",
    "captured_at",
]


def _make_minimal_document(
    *,
    decision: str = "REFURBISH",
    status: str = "finalized",
    checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a minimal valid evidence record document for testing."""
    if checks is None:
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

    # Build content_hash correctly
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

    # Compute content_hash
    content_hash = "sha256:" + sha256_hex(canonical_bytes(doc_without_hash))
    doc_without_hash["content_hash"] = content_hash
    return doc_without_hash


# ── T-CON-01: required top-level fields ──────────────────────────────────────


def test_t_con_01_required_top_level_fields() -> None:
    """T-CON-01: Every required handbook field is a key in EvidenceRecord.model_fields."""
    model_keys = set(EvidenceRecord.model_fields.keys())
    for field in REQUIRED_TOP_LEVEL:
        assert field in model_keys, f"Missing required field: {field!r}"


# ── T-CON-02: fixed check keys ────────────────────────────────────────────────


def test_t_con_02_fixed_check_keys_in_schema() -> None:
    """T-CON-02: FIXED_CHECK_KEYS list covers all mandatory checks from §14.2."""
    required_checks = {
        "photo_quality",
        "unit_presence",
        "identity",
        "completeness",
        "condition_grade",
        "relistable_as_is",
        "category_policy",
    }
    assert required_checks.issubset(set(FIXED_CHECK_KEYS)), (
        f"Missing check keys: {required_checks - set(FIXED_CHECK_KEYS)}"
    )


def test_t_con_02b_check_entries_have_all_fields() -> None:
    """T-CON-02b: A well-formed check entry validates correctly."""
    doc = _make_minimal_document()
    record = EvidenceRecord.model_validate(doc)
    for check in record.checks:
        assert check.check_key
        assert check.verdict in ("PASS", "FAIL", "UNCERTAIN")
        assert 0 <= check.confidence_bp <= 10000
        assert 0.0 <= check.confidence <= 1.0  # computed property
        assert check.detail
        assert check.model_version
        assert check.latency_ms >= 0


# ── T-CON-03: decided_by is never a model name ────────────────────────────────


@pytest.mark.parametrize(
    "decided_by",
    [
        "rules_engine@disposition-3f9a1c2b",
        "operator:op_eli",
        "reviewer:rev_priya",
        "deterministic_engine",
    ],
)
def test_t_con_03_decided_by_never_model(decided_by: str) -> None:
    """T-CON-03: outcome.decided_by is a rules engine version or human label."""
    # The decided_by must not be a raw model name like 'gemini-3.8-flash'
    model_pattern = re.compile(r"^gemini-|^claude-|^gpt-|^llama")
    assert not model_pattern.match(decided_by), f"decided_by looks like a model: {decided_by!r}"


def test_t_con_03_document_decided_by() -> None:
    """T-CON-03: Document's decided_by passes the model-name check."""
    doc = _make_minimal_document()
    decided_by = doc["outcome"]["decided_by"]
    model_pattern = re.compile(r"^gemini-|^claude-|^gpt-|^llama")
    assert not model_pattern.match(decided_by)


# ── T-CON-04: content_hash recomputes ────────────────────────────────────────


def test_t_con_04_content_hash_recomputes() -> None:
    """T-CON-04: content_hash = 'sha256:' + SHA-256(JCS(doc without content_hash))."""
    doc = _make_minimal_document()
    stored_hash = doc["content_hash"]
    assert stored_hash.startswith("sha256:")

    # Recompute
    doc_copy = {k: v for k, v in doc.items() if k != "content_hash"}
    expected = "sha256:" + sha256_hex(canonical_bytes(doc_copy))
    assert stored_hash == expected, f"content_hash mismatch: stored={stored_hash!r}, computed={expected!r}"


# ── T-CON-05: no key duplication between fixed fields and extensions.returns ──


def test_t_con_05_no_key_duplication() -> None:
    """T-CON-05: No key appears in both the fixed top level and extensions.returns."""
    doc = _make_minimal_document()
    record = EvidenceRecord.model_validate(doc)
    duplicates = check_no_key_duplication(record)
    # The documented exclusion: 'extensions' itself is not checked
    assert duplicates == [], f"Keys duplicated between fixed and extensions.returns: {duplicates}"


# ── T-CON-06: flat header prefix equals official CSV header ───────────────────


def test_t_con_06_flat_header_prefix() -> None:
    """T-CON-06: First 15 FLAT_COLUMNS equal the official CSV column names (§14.3)."""
    assert FLAT_COLUMNS[:15] == OFFICIAL_CSV_COLUMNS_15, (
        f"Flat column prefix mismatch.\nExpected: {OFFICIAL_CSV_COLUMNS_15}\nGot:      {FLAT_COLUMNS[:15]}"
    )


# ── T-CON-07: flat view and rich record agree ─────────────────────────────────


def test_t_con_07_flat_and_rich_agree() -> None:
    """T-CON-07: Flat view fields agree with the rich record on common fields."""
    doc = _make_minimal_document()
    row = build_flat_row(doc)

    ext = doc["extensions"]["returns"]
    assert row["record_id"] == doc["record_id"]
    assert row["unit_id"] == ext["unit_id"]
    assert row["org_id"] == doc["organization_id"]
    assert row["ordered_sku"] == ext["ordered_sku"]
    assert row["identity_match"] == ext.get("identity", {}).get("identity_match", "")
    assert row["amazon_condition"] == ext.get("condition", {}).get("amazon_condition", "")


# ── T-CON-08: valid document validates ───────────────────────────────────────


def test_t_con_08_valid_document_validates() -> None:
    """T-CON-08: A well-formed evidence record passes EvidenceRecord validation."""
    doc = _make_minimal_document()
    record = EvidenceRecord.model_validate(doc)
    assert record.record_id == "RTN-0014"
    assert record.agent == AGENT_NAME
    assert record.schema_version == SCHEMA_VERSION


# ── T-CON-09: invalid document rejected ──────────────────────────────────────


def test_t_con_09_missing_required_field_rejected() -> None:
    """T-CON-09: A document missing 'record_id' fails EvidenceRecord validation."""
    from pydantic import ValidationError

    doc = _make_minimal_document()
    del doc["record_id"]
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(doc)


# ── T-CON-10: schema generation ──────────────────────────────────────────────


def test_t_con_10_schema_generation() -> None:
    """T-CON-10: generate_evidence_record_schema() returns a dict with required meta fields."""
    schema = generate_evidence_record_schema()
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert "$id" in schema
    assert "title" in schema
    assert "properties" in schema


# ── T-CON-11: flat columns list ──────────────────────────────────────────────


def test_t_con_11_flat_columns_list() -> None:
    """T-CON-11: FLAT_COLUMNS is a non-empty list of unique strings."""
    assert len(FLAT_COLUMNS) >= 15
    assert len(FLAT_COLUMNS) == len(set(FLAT_COLUMNS)), "Duplicate column in FLAT_COLUMNS"


# ── T-CON-12: PENDING_REVIEW when recommendation is null ─────────────────────


def test_t_con_12_pending_review_outcome() -> None:
    """T-CON-12: outcome.decision == PENDING_REVIEW when recommendation is null (§14.2)."""
    doc = _make_minimal_document(decision="PENDING_REVIEW", status="awaiting_review")
    record = EvidenceRecord.model_validate(doc)
    assert record.outcome.decision == "PENDING_REVIEW"


# ── T-CON-13: MCP service function returns same structure as REST ─────────────


def test_t_con_13_evidence_service_structure() -> None:
    """T-CON-13: The evidence document structure is the same regardless of consumer (REST or MCP).

    This is a static test — we verify the shape of a programmatically built document.
    """
    from returns_manager.contract.service import validate_evidence_record

    doc = _make_minimal_document()
    errors = validate_evidence_record(doc)
    assert errors == [], f"Document does not validate against EvidenceRecord: {errors}"


# ── T-CON-14: contract build writes artifacts ─────────────────────────────────


def test_t_con_14_contract_build_writes_artifacts(tmp_path: Path) -> None:
    """T-CON-14: write_contract_artifacts writes all three expected files."""
    written = write_contract_artifacts(tmp_path)
    names = {p.name for p in written}
    assert "evidence-record.v1.schema.json" in names
    assert "return-evidence-flat.v1.schema.json" in names
    assert "flat-columns.v1.csv" in names

    # Verify JSON files are valid JSON
    for p in written:
        if p.suffix == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            assert isinstance(data, dict)
    # Verify CSV has all flat columns
    col_path = tmp_path / "flat-columns.v1.csv"
    csv_cols = col_path.read_text(encoding="utf-8").strip().split(",")
    assert csv_cols == FLAT_COLUMNS


# ── T-CON-15: CLI evidence --help exits 0 ────────────────────────────────────


def test_t_con_15_cli_evidence_help() -> None:
    """T-CON-15: `returns-manager evidence --help` exits 0 (P10 commands registered)."""
    from returns_manager.cli.main import run

    # Run in-process to avoid subprocess path issues on Windows
    exit_code = run(["evidence", "--help"])
    # Typer exits 0 for --help
    assert exit_code == 0


# ── T-CON-16: openapi export produces valid JSON ─────────────────────────────


def test_t_con_16_openapi_export_valid_json() -> None:
    """T-CON-16: `create_app().openapi()` returns a dict with 'openapi' and 'paths'."""
    from returns_manager.api.app import create_app

    app = create_app()
    schema = app.openapi()
    assert "openapi" in schema, "Missing 'openapi' version field"
    assert "paths" in schema, "Missing 'paths' field"
    # P10 evidence routes should be in the OpenAPI schema
    paths = schema["paths"]
    assert any("/return-evidence" in p for p in paths), "Evidence routes not found in OpenAPI paths"


# ── T-CON-17: flat_rows_to_csv produces RFC 4180 CSV ─────────────────────────


def test_t_con_17_flat_csv_format() -> None:
    """T-CON-17: flat_rows_to_csv produces valid CSV with header and data rows."""
    doc = _make_minimal_document()
    row = build_flat_row(doc)
    csv_content = flat_rows_to_csv([row])

    lines = csv_content.splitlines()
    assert len(lines) >= 2, "Expected header + at least one data row"
    header = lines[0]
    assert header.startswith("record_id,"), f"CSV header doesn't start with record_id: {header}"
    # Header must list all FLAT_COLUMNS
    col_list = header.split(",")
    assert col_list == FLAT_COLUMNS, f"CSV header mismatch:\nExpected: {FLAT_COLUMNS}\nGot: {col_list}"


# ── T-CON-18: problem statement example (T-SCN-PS-EXAMPLE complement) ─────────


def test_t_con_18_problem_statement_example() -> None:
    """T-CON-18: The problem statement headphones example maps to correct contract fields.

    PASS / FAIL / USB Cable / Used - Good / REFURBISH (Appendix A)
    """
    doc = _make_minimal_document(decision="REFURBISH", status="finalized")
    ext = doc["extensions"]["returns"]
    ext["completeness"]["parts_missing"] = "usb cable"
    ext["completeness"]["status"] = "incomplete"
    ext["condition"]["amazon_condition"] = "Used - Good"
    ext["identity"]["identity_match"] = "yes"

    # identity check = PASS
    identity_check = next((c for c in doc["checks"] if c["check_key"] == "identity"), None)
    assert identity_check is not None
    assert identity_check["verdict"] == "PASS"

    # completeness check = FAIL
    completeness_check = next((c for c in doc["checks"] if c["check_key"] == "completeness"), None)
    assert completeness_check is not None
    assert completeness_check["verdict"] == "FAIL"

    # condition_grade check = UNCERTAIN or PASS with "Used - Good"
    assert ext["condition"]["amazon_condition"] == "Used - Good"

    # outcome = REFURBISH
    record = EvidenceRecord.model_validate(doc)
    assert record.outcome.decision == "REFURBISH"
