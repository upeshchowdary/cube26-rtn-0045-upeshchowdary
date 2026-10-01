"""Batch auto-approve (A5): a flag on rows the deterministic engine already settled, never a decision.

A row is auto-approved only when every one of these holds for its real pipeline result:

- the engine recommended one of the four routes (no gate, no rule gap);
- the engine requires neither review nor sign-off (so S01 dispose and S02 high value are never
  auto-approved), and the pipeline raised no review reason or escalation trigger;
- every check passed, and every check's confidence (the model-reported confidence, in basis
  points) is at least `RM_BATCH_AUTO_APPROVE_MIN_CONFIDENCE_BP`;
- the model explicitly matched the returned product to the sold product, and did not report damage;
- every sold-vs-returned ID field is present on both records and agrees (a blank ID is "not
  checked", which blocks approval just like a mismatch).

It never changes the route, the rule id or the grade: it only lets the engine's own route stand
as `operator_disposition` without a person accepting it first. Other rows keep
`operator_disposition=pending_review`; proven mismatches are separately marked
`auto_disapproved`. The UI reads these flags from the backend.

The threshold is NOT yet calibrated by a threshold sweep (§21.5); see `config.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AutoApproval:
    approved: bool
    min_confidence_bp: int | None  # lowest check confidence, or None when there are no checks
    threshold_bp: int
    blocked_by: tuple[str, ...]  # every reason it was not approved (empty when approved)

    def as_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "min_confidence_bp": self.min_confidence_bp,
            "threshold_bp": self.threshold_bp,
            "threshold_calibrated": False,  # §21.5 sweep not yet run
            "blocked_by": list(self.blocked_by),
        }


def evaluate(result: Any, *, id_mismatch: bool, id_not_checked: bool, threshold_bp: int) -> AutoApproval:
    """`result` is a `judgment.pipeline.PipelineResult` from a real model response."""
    decision = result.decision
    blocked: list[str] = []
    if decision.recommended_disposition is None:
        blocked.append(f"no_recommendation:{decision.no_recommendation_reason or 'none'}")
    if decision.requires_review or result.requires_review:
        blocked.append("requires_review")
    if decision.requires_signoff:
        blocked.append("requires_signoff")
    if result.escalation_triggers:
        blocked.append("escalation_triggered")
    if id_mismatch:
        blocked.append("sold_vs_returned_id_mismatch")
    if id_not_checked:
        blocked.append("sold_vs_returned_id_not_checked")

    judgment = result.judgment
    if result.identity.identity_match != "yes":  # the fused verdict the engine decided on
        blocked.append("image_identity_not_matched")
    if judgment.model_observed_state == "damaged":
        blocked.append("damage_observed")

    checks = tuple(result.checks)
    if not checks:
        blocked.append("no_checks")
    if any(c.verdict != "PASS" for c in checks):
        blocked.append("check_not_passed")
    min_bp = min((c.confidence_bp for c in checks), default=None)
    if min_bp is not None and min_bp < threshold_bp:
        blocked.append("confidence_below_threshold")

    return AutoApproval(
        approved=not blocked, min_confidence_bp=min_bp, threshold_bp=threshold_bp, blocked_by=tuple(blocked)
    )
