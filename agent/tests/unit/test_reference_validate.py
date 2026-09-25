"""Unit and database tests for reference data validation, hashing, and loading (§8, P2)."""

from __future__ import annotations

import pytest
import yaml

from returns_manager.config import REPO_ROOT
from returns_manager.db.pool import Database
from returns_manager.reference.hashing import (
    compute_reference_content_sha256,
    verify_reference_content_sha256,
)
from returns_manager.reference.models import (
    CategoryPolicyV1,
    ProductCardV1,
)
from returns_manager.reference.validator import ReferenceValidator

REF_DIR = REPO_ROOT / "reference"


def test_reference_validate_all_succeeds() -> None:
    validator = ReferenceValidator(REF_DIR)
    validator.run_all()
    assert len(validator.errors) == 0, f"Validation errors: {validator.errors}"
    assert len(validator.validated_files) >= 34


def test_reference_hashing_detects_tampering() -> None:
    sample_data = {
        "schema": "category-policy/v1",
        "version": "1.0.0",
        "category_key": "electronics",
        "policy_id": "test-policy",
    }
    sha = compute_reference_content_sha256(sample_data)
    sample_data["content_sha256"] = sha
    assert verify_reference_content_sha256(sample_data) is True

    # Tamper with a field
    tampered = dict(sample_data)
    tampered["category_key"] = "pet"
    assert verify_reference_content_sha256(tampered) is False

    # Missing hash
    no_hash = dict(sample_data)
    del no_hash["content_sha256"]
    assert verify_reference_content_sha256(no_hash) is False


def test_active_rubrics_cover_all_categories() -> None:
    active_path = REF_DIR / "rubrics" / "active.yaml"
    assert active_path.exists()
    active_doc = yaml.safe_load(active_path.read_text(encoding="utf-8"))
    assert verify_reference_content_sha256(active_doc) is True

    snapshots = active_doc["active_snapshots"]
    expected_categories = [
        "electronics",
        "toys_games",
        "home_kitchen",
        "pet",
        "beauty_topical",
        "grocery_ingestible",
    ]
    for cat in expected_categories:
        assert cat in snapshots, f"Category {cat} missing from active rubrics"
        snap_id = snapshots[cat]
        rubric_file = REF_DIR / "rubrics" / "amazon.co.uk" / f"{cat}.yaml"
        assert rubric_file.exists(), f"Rubric file for {cat} not found: {rubric_file}"
        rubric_data = yaml.safe_load(rubric_file.read_text(encoding="utf-8"))
        assert rubric_data["snapshot_id"] == snap_id
        assert rubric_data["verification_status"] == "unverified_substitute"


def test_category_policies_have_source_types() -> None:
    policies_dir = REF_DIR / "policies" / "amazon.co.uk"
    policy_files = list(policies_dir.glob("*.yaml"))
    assert len(policy_files) >= 6

    valid_sources = {"amazon_guideline", "business_policy", "assumption"}
    for pf in policy_files:
        raw = yaml.safe_load(pf.read_text(encoding="utf-8"))
        policy = CategoryPolicyV1.model_validate(raw)
        assert verify_reference_content_sha256(raw) is True
        for field_name, fld in policy.fields.items():
            assert fld.source_type in valid_sources, (
                f"[{pf.name}] Field {field_name} has invalid source_type: {fld.source_type}"
            )
            assert fld.source_ref, f"[{pf.name}] Field {field_name} missing source_ref"


def test_product_cards_schema_and_uniqueness() -> None:
    products_dir = REF_DIR / "products"
    card_files = list(products_dir.glob("*/*.yaml"))
    assert len(card_files) >= 15

    for cf in card_files:
        raw = yaml.safe_load(cf.read_text(encoding="utf-8"))
        card = ProductCardV1.model_validate(raw)
        assert verify_reference_content_sha256(raw) is True
        # Check component ids are unique within card
        c_ids = [c.id for c in card.components]
        assert len(c_ids) == len(set(c_ids)), f"Duplicate component IDs in {cf.name}"
        # Check at least one component
        assert len(card.components) >= 1


@pytest.mark.db
async def test_db_reference_data_isolation(db: Database) -> None:
    """Test that products loaded into Supabase obey RLS tenant isolation."""
    # Under org_demo_alpha, query products
    async with db.transaction("org_demo_alpha") as conn:
        res = await conn.execute("SELECT sku, org_id FROM rm.products ORDER BY sku")
        alpha_rows = await res.fetchall()
        assert len(alpha_rows) > 0
        for r in alpha_rows:
            assert r["org_id"] == "org_demo_alpha"

    # Under org_demo_bravo, query products
    async with db.transaction("org_demo_bravo") as conn:
        res = await conn.execute("SELECT sku, org_id FROM rm.products ORDER BY sku")
        bravo_rows = await res.fetchall()
        assert len(bravo_rows) > 0
        for r in bravo_rows:
            assert r["org_id"] == "org_demo_bravo"

    # Both orgs see strictly their own products
    assert all(r["org_id"] == "org_demo_alpha" for r in alpha_rows)
    assert all(r["org_id"] == "org_demo_bravo" for r in bravo_rows)
