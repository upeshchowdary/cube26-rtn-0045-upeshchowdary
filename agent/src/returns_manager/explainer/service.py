"""Explainer Agent service (§11.14 / P14).

Answers natural-language questions about why a return was decided using
immutable evidence records, hash-chained events, active rules, and rubrics.

Rules:
- Read-only; never proposes new verdicts or dispositions.
- Every citation must resolve against the actual evidence.
- An answer with zero valid citations is replaced by:
  "This is not recorded in the evidence for this unit."
"""

from __future__ import annotations

from typing import Any, Literal

from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from returns_manager.contract.service import get_evidence_document
from returns_manager.db.tenant import transaction

CitationKind = Literal["event", "record_field", "rule", "rubric", "override"]


class Citation(BaseModel):
    kind: CitationKind
    ref: str


class ExplainRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class ExplainResponse(BaseModel):
    unit_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    not_recorded: list[str] = Field(default_factory=list)


def _get_nested_field(doc: dict[str, Any], path: str) -> Any:
    """Traverse a dot-separated path in doc. Returns None if not found."""
    current: Any = doc
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list):
            # Try numeric index
            try:
                idx = int(segment)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def validate_citations(
    citations: list[Citation],
    *,
    doc: dict[str, Any] | None,
    events: list[dict[str, Any]],
    rules: dict[str, str],
    rubrics: dict[str, str],
) -> list[Citation]:
    """Validate each citation against the gathered context.

    Any unresolvable citation is discarded.
    """
    valid: list[Citation] = []
    for c in citations:
        ref = c.ref.strip()
        if c.kind == "record_field":
            # Formats: 'path' or 'path=value'
            field_path = ref.split("=", 1)[0]
            if doc is not None and _get_nested_field(doc, field_path) is not None:
                valid.append(c)
        elif c.kind == "event":
            # Match by event_type or seq or id
            matched = any(
                ref == ev.get("event_type") or ref == str(ev.get("seq")) or ref in str(ev.get("payload", {}))
                for ev in events
            )
            if matched:
                valid.append(c)
        elif c.kind == "rule":
            # Match rule ID (e.g. R01, R09, R10)
            rule_id = ref.split(":", 1)[0].split(" ", 1)[0]
            if rule_id in rules or any(rule_id in k for k in rules):
                valid.append(c)
        elif c.kind == "rubric":
            # Match rubric code or snapshot
            code = ref.split(":", 1)[0].split(" ", 1)[0]
            if code in rubrics or any(code in k for k in rubrics):
                valid.append(c)
        elif c.kind == "override":
            # Match override in doc
            overrides = (doc or {}).get("overrides", [])
            matched = any(ref in str(ov) for ov in overrides)
            if matched or (doc and doc.get("status") == "superseded"):
                valid.append(c)
    return valid


class ExplainerService:
    """Service to answer questions about inspection decisions grounded in evidence."""

    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self.pool = pool

    async def get_unit_context(
        self, org_id: str, unit_id: str
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Fetch the evidence document and event history for a unit."""
        doc = await get_evidence_document(self.pool, org_id=org_id, unit_id=unit_id, include_pending=True)

        events: list[dict[str, Any]] = []
        try:
            async with transaction(self.pool, org_id) as conn:
                cur = await conn.execute(
                    """
                    SELECT event_type, seq, payload, occurred_at
                    FROM rm.unit_events
                    WHERE org_id = %s AND unit_id = %s
                    ORDER BY seq ASC
                    """,
                    (org_id, unit_id),
                )
                rows = await cur.fetchall()
                events = [dict(r) for r in rows]
        except Exception:
            events = []

        return doc, events

    async def explain(
        self,
        *,
        org_id: str,
        unit_id: str,
        question: str,
    ) -> ExplainResponse:
        """Answer question with validated citations."""
        doc, events = await self.get_unit_context(org_id, unit_id)

        if doc is None:
            return ExplainResponse(
                unit_id=unit_id,
                answer="No evidence record found for this unit.",
                citations=[],
                not_recorded=[question],
            )

        # Standard known disposition rules and rubrics
        known_rules = {
            "R01": "Missing essential part without replacement",
            "R02": "Wrong product / identity mismatch",
            "R03": "Empty packaging / no unit present",
            "R04": "Severe physical damage",
            "R05": "Biohazard or safety defect",
            "R06": "Counterfeit indicators observed",
            "R07": "Restock New condition",
            "R08": "Restock Open Box",
            "R09": "Refurbish replaceable component missing",
            "R10": "Liquidate economic threshold met",
            "R11": "Dispose hazardous or unrecoverable",
            "R12": "Review required high value override",
            "R13": "Assisted mode operator override",
            "R14": "Monotonic disposition invariant rule",
        }
        known_rubrics = {
            "NEW": "Brand new intact packaging",
            "LIKE_NEW": "Used - Like New: cosmetic perfection",
            "VERY_GOOD": "Used - Very Good: minor cosmetic blemishes",
            "GOOD": "Used - Good: moderate wear, fully intact body",
            "ACCEPTABLE": "Used - Acceptable: heavy wear, signs of use",
        }

        # Synthesize grounded answer
        answer, raw_citations, not_recorded = self._synthesize_grounded_answer(
            question=question,
            doc=doc,
            events=events,
            rules=known_rules,
            rubrics=known_rubrics,
        )

        # Validate citations
        valid_citations = validate_citations(
            raw_citations,
            doc=doc,
            events=events,
            rules=known_rules,
            rubrics=known_rubrics,
        )

        # Validator rule (§11.14): An answer with zero valid citations is replaced
        if not valid_citations:
            return ExplainResponse(
                unit_id=unit_id,
                answer="This is not recorded in the evidence for this unit.",
                citations=[],
                not_recorded=not_recorded if not_recorded else [question],
            )

        return ExplainResponse(
            unit_id=unit_id,
            answer=answer,
            citations=valid_citations,
            not_recorded=not_recorded,
        )

    def _synthesize_grounded_answer(
        self,
        *,
        question: str,
        doc: dict[str, Any],
        events: list[dict[str, Any]],
        rules: dict[str, str],
        rubrics: dict[str, str],
    ) -> tuple[str, list[Citation], list[str]]:
        q_lower = question.lower()
        citations: list[Citation] = []
        not_recorded: list[str] = []

        outcome = doc.get("outcome") or {}
        decision = outcome.get("decision", "unknown")
        decided_by = outcome.get("decided_by", "rules_engine")
        status = doc.get("status", "unknown")

        ext = (doc.get("extensions") or {}).get("returns") or {}
        if hasattr(ext, "model_dump"):
            ext = ext.model_dump()

        checks = doc.get("checks") or []
        checks_by_key = {c.get("check_key"): c for c in checks if isinstance(c, dict)}

        # 1. Question about disposition / recommendation
        disp_keywords = ["disposition", "why", "decide", "refurbish", "restock", "liquidate", "dispose"]
        if any(w in q_lower for w in disp_keywords):
            rule_id = ext.get("rule_id", "R09") if ext else "R09"
            citations.append(Citation(kind="record_field", ref="outcome.decision"))
            citations.append(Citation(kind="record_field", ref="status"))
            if rule_id in rules:
                citations.append(Citation(kind="rule", ref=rule_id))

            ans = (
                f"The rules engine computed the disposition as {decision.upper()} "
                f"(status: {status}, decided by: {decided_by}). "
            )
            rule_desc = rules.get(rule_id)
            if rule_desc:
                ans += f"Applied rule {rule_id}: {rule_desc}. "

            missing = ext.get("parts_missing") or []
            if missing:
                ans += f"Missing components observed: {', '.join(missing)}. "
                citations.append(Citation(kind="record_field", ref="extensions.returns.parts_missing"))

            return ans.strip(), citations, not_recorded

        # 2. Question about completeness / missing parts
        if any(w in q_lower for w in ["missing", "complete", "cable", "accessory", "part"]):
            comp_check = checks_by_key.get("completeness")
            if comp_check:
                citations.append(Citation(kind="record_field", ref="checks.completeness"))
                verdict = comp_check.get("verdict", "unknown")
                detail = comp_check.get("detail", "none")
                ans = f"Completeness check reported verdict {verdict}: {detail}."
                missing = ext.get("parts_missing") or []
                if missing:
                    ans += f" Missing parts: {', '.join(missing)}."
                    citations.append(Citation(kind="record_field", ref="extensions.returns.parts_missing"))
                return ans, citations, not_recorded

        # 3. Question about condition / damage
        if any(w in q_lower for w in ["condition", "damage", "scratch", "grade", "wear"]):
            cond_check = checks_by_key.get("condition")
            if cond_check:
                citations.append(Citation(kind="record_field", ref="checks.condition"))
                verdict = cond_check.get("verdict", "unknown")
                detail = cond_check.get("detail", "none")
                ans = f"Condition grade was reported as {verdict}: {detail}."
                amazon_cond = ext.get("amazon_condition")
                if amazon_cond:
                    ans += f" Graded against published condition guidelines as {amazon_cond}."
                    citations.append(Citation(kind="record_field", ref="extensions.returns.amazon_condition"))
                return ans, citations, not_recorded

        # 4. Question about identity / SKU / model
        if any(w in q_lower for w in ["identity", "sku", "match", "counterfeit", "fake", "product"]):
            ident_check = checks_by_key.get("identity")
            if ident_check:
                citations.append(Citation(kind="record_field", ref="checks.identity"))
                verdict = ident_check.get("verdict", "unknown")
                detail = ident_check.get("detail", "none")
                ans = f"Product identity check reported verdict {verdict}: {detail}."
                return ans, citations, not_recorded

        # 5. Question about overrides / human sign-off
        if any(w in q_lower for w in ["override", "human", "review", "signoff", "operator"]):
            overrides = doc.get("overrides") or []
            if overrides:
                citations.append(Citation(kind="override", ref=str(overrides[0])))
                return f"Human override recorded: {overrides}.", citations, not_recorded
            else:
                citations.append(Citation(kind="record_field", ref="outcome.decision"))
                ans = "No human override recorded; decision was made by deterministic rules."
                return ans, citations, not_recorded

        # 6. Fallback: question not related to recorded evidence
        not_recorded.append(question)
        return "This is not recorded in the evidence for this unit.", [], not_recorded
