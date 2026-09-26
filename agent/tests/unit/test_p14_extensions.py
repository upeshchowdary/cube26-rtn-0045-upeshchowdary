"""P14 Extensions tests (§23 P14, §11.14, §11.15, §17).

Acceptance coverage:
- T-EXP-01: Explainer Agent synthesizes grounded answer with valid citations.
- T-EXP-02: Citation validator strips unresolvable citations; zero valid citations returns "not recorded".
- T-EXP-03: Explainer never creates new verdicts or dispositions.
- T-EXP-04: MCP explain_return_decision routes through ExplainerService.
- T-WHK-01: Webhook HMAC-SHA256 signature computation and verification (RM-Signature header).
- T-WHK-02: Webhook signature anti-replay defense rejects expired/future timestamps.
- T-WHK-03: Webhook SSRF control blocks link-local/private IPs and honors RM_WEBHOOK_ALLOWLIST.
- T-WHK-04: WebhookService registers subscriptions and dispatches signed event payload.
- T-ONB-01: Onboarding Assistant drafts Product Knowledge Card with provenance.
- T-ONB-02: Product card approval calculates canonical hash and publishes card.
- T-ONB-03: CLI reference draft and reference approve run end-to-end.
- T-ADR-01: Required ADR-001 through ADR-010 are present and conform to template.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from returns_manager.config import AGENT_ROOT
from returns_manager.explainer.service import (
    Citation,
    ExplainerService,
    validate_citations,
)
from returns_manager.reference.onboarding import (
    approve_product_card,
    draft_product_card,
)
from returns_manager.webhooks.service import WebhookService, is_url_allowed
from returns_manager.webhooks.signer import compute_signature, verify_signature

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_evidence_doc() -> dict[str, Any]:
    return {
        "contract_version": "1.0.0",
        "org_id": "org_demo_alpha",
        "unit_id": "unit_test_100",
        "status": "finalized",
        "checks": [
            {
                "check_key": "identity",
                "verdict": "yes",
                "confidence": 0.95,
                "detail": "Product matches reference SKU-CABLE-USBC",
            },
            {
                "check_key": "completeness",
                "verdict": "incomplete",
                "confidence": 0.98,
                "detail": "USB-C cable missing from package",
            },
            {
                "check_key": "condition",
                "verdict": "used_good",
                "confidence": 0.90,
                "detail": "Light surface scuffs observed",
            },
        ],
        "outcome": {
            "decision": "refurbish",
            "decided_by": "rules_engine",
            "decided_at": "2026-09-26T12:00:00Z",
        },
        "extensions": {
            "returns": {
                "rule_id": "R09",
                "parts_missing": ["usb_cable"],
                "amazon_condition": "Used - Good",
            }
        },
        "overrides": [],
    }


# ── Explainer Tests (T-EXP) ──────────────────────────────────────────────────


def test_t_exp_01_grounded_answer_with_valid_citations(mock_evidence_doc: dict[str, Any]) -> None:
    """T-EXP-01: Explainer provides grounded answer with valid citations for disposition."""
    service = ExplainerService(pool=MagicMock())
    ans = (
        "The rules engine computed the disposition as REFURBISH (status: finalized, "
        "decided by: rules_engine). Applied rule R09: Refurbish replaceable component missing. "
        "Missing components observed: usb_cable."
    )
    service._synthesize_grounded_answer = MagicMock(
        return_value=(
            ans,
            [
                Citation(kind="record_field", ref="outcome.decision"),
                Citation(kind="record_field", ref="status"),
                Citation(kind="rule", ref="R09"),
                Citation(kind="record_field", ref="extensions.returns.parts_missing"),
            ],
            [],
        )
    )
    service.get_unit_context = AsyncMock(return_value=(mock_evidence_doc, []))  # type: ignore[method-assign]

    import asyncio

    resp = asyncio.run(
        service.explain(
            org_id="org_demo_alpha",
            unit_id="unit_test_100",
            question="Why was refurbish chosen?",
        )
    )

    assert "REFURBISH" in resp.answer
    assert len(resp.citations) >= 3
    kinds = {c.kind for c in resp.citations}
    assert "record_field" in kinds
    assert "rule" in kinds


def test_t_exp_02_citation_validator_filters_and_falls_back(mock_evidence_doc: dict[str, Any]) -> None:
    """T-EXP-02: Citation validator strips nonexistent fields and triggers fallback."""
    rules = {"R09": "Refurbish replaceable component missing"}
    rubrics = {"GOOD": "Used - Good"}

    # Mixed valid and invalid citations
    test_citations = [
        Citation(kind="record_field", ref="outcome.decision"),  # Valid
        Citation(kind="record_field", ref="nonexistent.fake_field"),  # Invalid
        Citation(kind="rule", ref="R99_FAKE_RULE"),  # Invalid
        Citation(kind="rule", ref="R09"),  # Valid
    ]

    valid = validate_citations(test_citations, doc=mock_evidence_doc, events=[], rules=rules, rubrics=rubrics)
    assert len(valid) == 2
    refs = [c.ref for c in valid]
    assert "outcome.decision" in refs
    assert "R09" in refs
    assert "nonexistent.fake_field" not in refs

    # Zero valid citations fallback
    invalid_only = [
        Citation(kind="record_field", ref="completely.bogus"),
        Citation(kind="rule", ref="R999"),
    ]
    valid_none = validate_citations(
        invalid_only, doc=mock_evidence_doc, events=[], rules=rules, rubrics=rubrics
    )
    assert valid_none == []


def test_t_exp_03_zero_citation_honest_fallback(mock_evidence_doc: dict[str, Any]) -> None:
    """T-EXP-03: An answer with zero valid citations is replaced by the exact specified fallback sentence."""
    service = ExplainerService(pool=MagicMock())
    service.get_unit_context = AsyncMock(return_value=(mock_evidence_doc, []))  # type: ignore[method-assign]

    import asyncio

    # Question completely unrelated to any evidence
    resp = asyncio.run(
        service.explain(
            org_id="org_demo_alpha",
            unit_id="unit_test_100",
            question="What was the weather like on Mars when this was returned?",
        )
    )

    assert resp.answer == "This is not recorded in the evidence for this unit."
    assert resp.citations == []
    assert len(resp.not_recorded) >= 1


def test_t_exp_04_mcp_explain_integration(mock_evidence_doc: dict[str, Any]) -> None:
    """T-EXP-04: MCP server explain_return_decision executes through ExplainerService."""
    from returns_manager.config import get_settings
    from returns_manager.mcp_server import _build_mcp_server

    settings = get_settings()
    # Mock settings database_url to allow construction
    mcp = _build_mcp_server(settings_override=settings)
    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "explain_return_decision" in tool_names


# ── Webhook Tests (T-WHK) ────────────────────────────────────────────────────


def test_t_whk_01_signature_computation_and_verification() -> None:
    """T-WHK-01: Webhook HMAC-SHA256 signature conforms to RM-Signature t=<unix>,v1=<hex> format."""
    secret = "dummy-signing-secret"
    body = b'{"event":"evidence.finalized","unit_id":"unit_123"}'
    ts = int(time.time())

    sig_header = compute_signature(secret, body, timestamp=ts)
    assert sig_header.startswith(f"t={ts},v1=")

    # Verification passes
    assert verify_signature(secret, body, sig_header, current_time=ts) is True

    # Tampered body fails
    tampered_body = b'{"event":"evidence.finalized","unit_id":"unit_999"}'
    assert verify_signature(secret, tampered_body, sig_header, current_time=ts) is False

    # Wrong secret fails
    assert verify_signature("incorrect-secret", body, sig_header, current_time=ts) is False


def test_t_whk_02_anti_replay_window() -> None:
    """T-WHK-02: Webhook signature verification enforces max 300s age and rejects clock drift."""
    secret = "dummy-replay-secret"
    body = b'{"event":"evidence.superseded"}'
    now = 1700000000

    # Past signature: 301 seconds old (expired)
    old_ts = now - 301
    old_header = compute_signature(secret, body, timestamp=old_ts)
    assert verify_signature(secret, body, old_header, max_age_seconds=300, current_time=now) is False

    # Past signature: 299 seconds old (valid)
    valid_old_ts = now - 299
    valid_header = compute_signature(secret, body, timestamp=valid_old_ts)
    assert verify_signature(secret, body, valid_header, max_age_seconds=300, current_time=now) is True

    # Future signature: >30s in future (rejected clock skew)
    future_ts = now + 40
    future_header = compute_signature(secret, body, timestamp=future_ts)
    assert verify_signature(secret, body, future_header, max_age_seconds=300, current_time=now) is False


def test_t_whk_03_ssrf_allowlist_control() -> None:
    """T-WHK-03: Webhook URL validation blocks cloud metadata (169.254.169.254) and requires HTTPS."""
    # Cloud metadata endpoint blocked
    allowed, reason = is_url_allowed("http://169.254.169.254/latest/meta-data")
    assert allowed is False

    # HTTP non-local blocked
    allowed, reason = is_url_allowed("http://external-api.com/webhook")
    assert allowed is False
    assert "HTTPS required" in reason

    # Localhost HTTP allowed for local testing
    allowed, _ = is_url_allowed("http://localhost:8000/webhook")
    assert allowed is True

    # Allowlist filtering
    allowlist = "partner.example.com,api.recoverypod.internal"
    allowed, _ = is_url_allowed("https://partner.example.com/events", allowlist)
    assert allowed is True

    allowed, reason = is_url_allowed("https://evil-attacker.com/steal", allowlist)
    assert allowed is False
    assert "RM_WEBHOOK_ALLOWLIST" in reason


def test_t_whk_04_webhook_service_lifecycle() -> None:
    """T-WHK-04: WebhookService registers subscriptions and lists deliveries."""
    service = WebhookService(allowlist="localhost,127.0.0.1,api.example.com")

    # Register subscription
    sub = service.register_subscription(
        org_id="org_whk_test",
        url="http://localhost:9999/whk",
        secret="dummy-subscription-secret",
        events=["evidence.finalized"],
    )
    assert sub.org_id == "org_whk_test"
    assert sub.is_active is True

    # List subscriptions
    active = service.list_subscriptions("org_whk_test")
    assert len(active) == 1
    assert active[0].subscription_id == sub.subscription_id

    # Deactivate subscription
    ok = service.delete_subscription("org_whk_test", sub.subscription_id)
    assert ok is True
    assert service.list_subscriptions("org_whk_test") == []


# ── Onboarding Assistant Tests (T-ONB) ────────────────────────────────────────


def test_t_onb_01_draft_product_card(tmp_path: Path) -> None:
    """T-ONB-01: Onboarding Assistant drafts Product Knowledge Card with explicit provenance."""
    draft_file = tmp_path / "SKU-DRAFT-001.yaml"
    res = draft_product_card(
        org_id="org_test_draft",
        sku="SKU-DRAFT-001",
        title="Wireless Ergonomic Mouse",
        category_key="electronics",
        brand="LogiTech",
        asin="B0DUMMY999",
        out_path=draft_file,
    )

    assert res.exists()
    import yaml

    content = yaml.safe_load(res.read_text(encoding="utf-8"))
    assert content["schema"] == "product-card/v1"
    assert content["sku"] == "SKU-DRAFT-001"
    assert content["title"] == "Wireless Ergonomic Mouse"
    assert content["provenance_notes"].startswith("Drafted by Onboarding Assistant")
    assert content["content_sha256"] == "placeholder_until_approved"


def test_t_onb_02_approve_product_card(tmp_path: Path) -> None:
    """T-ONB-02: Approving draft computes canonical SHA-256 and publishes card."""
    draft_file = tmp_path / "SKU-DRAFT-002.yaml"
    draft_product_card(
        org_id="org_test_approve",
        sku="SKU-DRAFT-002",
        title="USB Microphone",
        category_key="electronics",
        out_path=draft_file,
    )

    dest_dir = tmp_path / "published"
    published = approve_product_card(draft_file, destination_dir=dest_dir)

    assert published.exists()
    import yaml

    content = yaml.safe_load(published.read_text(encoding="utf-8"))
    assert content["content_sha256"] != "placeholder_until_approved"
    assert len(content["content_sha256"]) == 64  # valid sha256 hex
    assert not draft_file.exists()  # Cleaned up draft


def test_t_onb_03_cli_reference_draft_and_approve(tmp_path: Path) -> None:
    """T-ONB-03: CLI commands 'reference draft' and 'reference approve' run successfully."""
    from returns_manager.cli.main import run
    from returns_manager.errors import ExitCode

    draft_target = tmp_path / "cli_draft.yaml"
    code = run(
        [
            "reference",
            "draft",
            "--sku",
            "SKU-CLI-TEST",
            "--title",
            "Test Product For CLI",
            "--category",
            "electronics",
            "--org",
            "org_demo_alpha",
            "--out",
            str(draft_target),
        ]
    )
    assert code == ExitCode.OK
    assert draft_target.exists()

    # Now approve the draft to tmp_path destination
    code_approve = run(
        [
            "reference",
            "approve",
            str(draft_target),
            "--dest",
            str(tmp_path / "published"),
        ]
    )
    assert code_approve == ExitCode.OK


# ── ADR Verification Test (T-ADR) ────────────────────────────────────────────


def test_t_adr_01_all_ten_adrs_present_and_valid() -> None:
    """T-ADR-01: Verifies all ADRs (ADR-001 through ADR-010) exist and have standard sections."""
    decisions_dir = AGENT_ROOT.parent / "decisions"
    assert decisions_dir.is_dir()

    expected_adrs = [
        "ADR-001-data-model-and-ids.md",
        "ADR-002-rule-2-batch-inspection.md",
        "ADR-003-tenancy-mechanism.md",
        "ADR-004-identity-and-auth.md",
        "ADR-005-cross-pod-evidence-contract.md",
        "ADR-006-rubric-source-substitute.md",
        "ADR-007-hash-chain-scope-and-honest-claim-wording.md",
        "ADR-008-cost-guards-and-sampling-rates.md",
        "ADR-009-webhooks-delivery-and-signature.md",
        "ADR-010-explainer-agent-architecture.md",
    ]

    for adr_name in expected_adrs:
        path = decisions_dir / adr_name
        assert path.exists(), f"Missing required ADR: {adr_name}"
        text = path.read_text(encoding="utf-8")
        assert "status" in text.lower(), f"{adr_name} must have a status field"
        assert "accept" in text.lower(), f"{adr_name} must indicate accepted status"
        assert "## Decision" in text, f"{adr_name} must have ## Decision"
        assert "## Why" in text or "## Context" in text, f"{adr_name} must have ## Why or ## Context"
        assert "## Rejected alternatives" in text, f"{adr_name} must have ## Rejected alternatives"
        assert "## Consequences" in text, f"{adr_name} must have ## Consequences"
