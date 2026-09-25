"""The judgment job handler (§3.3, §11).

references → context → model session → deterministic pipeline → persist.

- Missing reference data (§11.2a): no model call; a `skipped` inspection run and an all-UNCERTAIN result are
  stored and the return goes to `awaiting_review` with the reason codes; photos stay intact.
- Model/provider failure: the failed run (requests, usage, paid-equivalent cost, error class) is stored in its
  own transaction and the error is re-raised so the worker fails open (§10.6).
- Success: the run, its tool calls and the result are written by `persist`, which the worker executes in the
  same transaction as the state transition (§11.7 step 12). Thinking content is never stored.
"""

from __future__ import annotations

import dataclasses
import json
import time
from typing import Any

from returns_manager.canonical.hashing import sha256_hex, sha256_jcs
from returns_manager.chain import event_types as ET
from returns_manager.chain.append import append_event
from returns_manager.config import Settings
from returns_manager.db.pool import Database
from returns_manager.disposition.engine import DispositionInputs, decide
from returns_manager.disposition.params import load_params, rules_version
from returns_manager.ids import new_id
from returns_manager.intake.quality import load_thresholds
from returns_manager.jobs.queue import JobRecord
from returns_manager.jobs.statemachine import ReturnStatus
from returns_manager.jobs.worker import HandlerResult
from returns_manager.judgment.pipeline import Check, PhotoGate, PipelineResult, run_pipeline
from returns_manager.llm.client import ModelClient
from returns_manager.llm.context import (
    ContextBundle,
    MissingReference,
    PhotoSource,
    assemble,
    load_photos,
    load_references,
    reference_bytes,
)
from returns_manager.llm.loop import SessionFailed, SessionTrace, run_session
from returns_manager.llm.prompts import get_prompt
from returns_manager.llm.quota import QuotaGuard
from returns_manager.llm.schemas import SCHEMA_VERSION
from returns_manager.security import controls


def _json(value: Any) -> str:
    def default(o: Any) -> Any:
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        return str(o)

    return json.dumps(value, default=default)


"""Hash method constants for evidence metadata.

RFC 8785 (JCS) is the canonical hashing method for integer-only payloads (reference
data, disposition inputs, event chains).  Model output contains decimal confidence
floats, which JCS rejects, so it uses a deterministic sorted-key JSON serialisation
instead.  These constants are stored alongside every hash so a future verifier knows
exactly how to reproduce it without reading the source code.
"""

OUTPUT_HASH_METHOD = "sha256-sorted-json-v1"
OUTPUT_HASH_DESCRIPTION = (
    "SHA-256 of json.dumps(output, allow_nan=False, ensure_ascii=False, "
    "separators=(',',':'), sort_keys=True).encode('utf-8').  "
    "Deterministic for valid JSON; refuses NaN/Infinity.  "
    "NOT RFC 8785: model output carries decimal floats which JCS rejects."
)
EVIDENCE_HASH_METHOD = "sha256-rfc8785-v1"
EVIDENCE_HASH_DESCRIPTION = (
    "SHA-256 of RFC 8785 JCS canonical bytes.  No floats allowed in the payload "
    "(basis points, minor units, strings only)."
)


def _output_sha256(output: dict[str, Any]) -> str:
    """Hash raw model JSON deterministically, including decimal confidences.

    Method: ``OUTPUT_HASH_METHOD`` (sorted-key JSON, not RFC 8785).
    See the module-level constants for the reproducible specification.
    """
    canonical = json.dumps(
        output,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256_hex(canonical)


@dataclasses.dataclass(frozen=True)
class GateFacts:
    gate: PhotoGate
    operator_state: str | None


async def _gate_facts(conn: Any, return_id: str) -> GateFacts:
    cur = await conn.execute(
        "SELECT quality_status, quality FROM rm.return_photos WHERE return_id = %s AND superseded = false",
        (return_id,),
    )
    rows = await cur.fetchall()
    non_fail = sum(1 for r in rows if r["quality_status"] != "fail")
    issues = {i for r in rows for i in ((r["quality"] or {}).get("issues") or [])}
    cur = await conn.execute(
        "SELECT observed_state FROM rm.operator_observations WHERE return_id = %s "
        "ORDER BY recorded_at DESC LIMIT 1",
        (return_id,),
    )
    obs = await cur.fetchone()
    # Submit refuses fewer than 2 non-failing photos unless the operator acknowledged the warnings (§9.4).
    return GateFacts(
        gate=PhotoGate(
            non_fail_photos=non_fail,
            acknowledged_warnings=non_fail < 2,
            integrity_flags=("possible_reused_photo",) if "possible_reused_photo" in issues else (),
        ),
        operator_state=obs["observed_state"] if obs else None,
    )


def inspection_config_version(bundle: ContextBundle, settings: Settings, rv: str) -> str:
    """§10.5: hash of everything that, when changed, makes a new inspection of the same photos meaningful."""
    m = bundle.manifest
    return sha256_jcs(
        {
            "prompts": [m["prompt"], m["task_prompt"]],
            "judgment_schema_version": SCHEMA_VERSION,
            "response_schema_sha256": m["response_schema_sha256"],
            "model": settings.rm_judgment_model,
            "thinking": settings.rm_judgment_thinking,
            "output_mode": settings.rm_output_mode,
            "rules_version": rv,
            "quality_gate_version": load_thresholds().version,
            "policy": m["policy"],
            "rubric": m["rubric"],
            "product_card": m["product_card"],
        }
    )


class JudgmentHandler:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        client: ModelClient,
        photos: PhotoSource,
        quota: QuotaGuard | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.client = client
        self.photos = photos
        self.quota = quota or QuotaGuard(db, settings)

    async def __call__(self, job: JobRecord) -> HandlerResult:
        eff = await controls.effective(self.db, job.org_id)
        auto = eff[controls.Control.AUTO_DISPOSITION].enabled
        async with self.db.transaction(job.org_id) as conn:
            facts = await _gate_facts(conn, job.return_id)
            # Fetch unit_id for the chain (needed in both success and skipped paths)
            cur = await conn.execute(
                "SELECT unit_id FROM rm.returns WHERE org_id = %s AND return_id = %s",
                (job.org_id, job.return_id),
            )
            ret_row = await cur.fetchone()
            unit_id: str = ret_row["unit_id"] if ret_row else job.return_id
            try:
                ret, card, others, rubric, policy = await load_references(conn, job.org_id, job.return_id)
                refs = reference_bytes(card, job.org_id)
                photos = await load_photos(conn, self.photos, job.return_id)
            except MissingReference as missing:
                return self._skipped(job, facts, missing, auto, unit_id)
        try:
            bundle = assemble(
                settings=self.settings,
                return_row=ret,
                card=card,
                other_cards=others,
                rubric=rubric,
                policy=policy,
                photos=photos,
                refs=refs,
            )
        except MissingReference as missing:
            return self._skipped(job, facts, missing, auto, unit_id)

        inspection_id = new_id()
        started = time.time()
        max_tokens = self.settings.rm_max_output_tokens
        if job.last_error_class == "truncated":  # §10.4: retry once with twice the output budget
            max_tokens = min(max_tokens * 2, 32000)
        try:
            session = await run_session(
                self.client, self.quota, bundle, self.settings, max_output_tokens=max_tokens
            )
        except SessionFailed as failed:
            await self._persist_failed_run(job, inspection_id, bundle, failed.trace, failed.cause)
            raise failed.cause from None

        ctx = dataclasses.replace(
            bundle.ctx,
            crop_aliases=session.crop_aliases,
            reference_aliases=bundle.ctx.reference_aliases + session.reference_aliases,
        )
        rv = rules_version(load_params())
        t0 = time.perf_counter()
        result = run_pipeline(
            session.judgment,
            ctx,
            photo_gate=facts.gate,
            rules_version=rv,
            auto_disposition_enabled=auto,
            operator_state=facts.operator_state,
        )
        det_ms = int((time.perf_counter() - t0) * 1000)
        config_version = inspection_config_version(bundle, self.settings, rv)
        target = ReturnStatus(result.target_status)
        output_sha = _output_sha256(session.raw_output) if session.raw_output else None

        async def persist(conn: Any) -> None:
            await self._insert_run(
                conn,
                job,
                inspection_id,
                bundle,
                session.trace,
                status="completed",
                started=started,
                output=session.raw_output,
                validation={
                    "actions": [dataclasses.asdict(a) for a in result.report.actions],
                    "invented_reference_count": result.report.invented_reference_count,
                    "invented_quote_count": result.report.invented_quote_count,
                },
                config_version=config_version,
            )
            for rec in session.trace.tools:
                await conn.execute(
                    """INSERT INTO rm.model_tool_calls (tool_call_id, org_id, inspection_id, seq, round_trip,
                         tool_name, input, output_summary, status, latency_ms)
                       VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)""",
                    (
                        new_id(),
                        job.org_id,
                        inspection_id,
                        rec.seq,
                        rec.round_trip,
                        rec.tool_name,
                        json.dumps(rec.input),
                        json.dumps(rec.output_summary),
                        rec.status,
                        rec.latency_ms,
                    ),
                )
            await self._insert_result(conn, job, inspection_id, result, session.trace, det_ms, rv)
            # ── P7: chain events (in the same transaction as the DB inserts) ──
            _actor = "system"
            await append_event(
                conn,
                org_id=job.org_id,
                unit_id=unit_id,
                return_id=job.return_id,
                event_type=ET.INSPECTION_STARTED,
                actor_type=_actor,
                actor_id=f"worker/{job.job_id}",
                payload={"inspection_id": inspection_id, "job_id": job.job_id, "kind": job.kind},
            )
            await append_event(
                conn,
                org_id=job.org_id,
                unit_id=unit_id,
                return_id=job.return_id,
                event_type=ET.INSPECTION_COMPLETED,
                actor_type=_actor,
                actor_id=f"worker/{job.job_id}",
                payload={
                    "inspection_id": inspection_id,
                    "output_sha256": output_sha or "",
                    "api_requests": session.trace.requests_sent,
                    "tool_calls": len(session.trace.tools),
                },
            )
            d = result.decision
            await append_event(
                conn,
                org_id=job.org_id,
                unit_id=unit_id,
                return_id=job.return_id,
                event_type=ET.DISPOSITION_COMPUTED,
                actor_type=_actor,
                actor_id=f"worker/{job.job_id}",
                payload={
                    "inspection_id": inspection_id,
                    "inputs_sha256": sha256_jcs(result.inputs.canonical()),
                    "rule_id": d.rule_id if hasattr(d, "rule_id") else "unknown",
                    "rules_version": rv,
                    "recommended_disposition": d.recommended_disposition,
                    "requires_review": result.requires_review,
                },
            )

        return HandlerResult(
            target_return_status=target, persist=persist, details={"inspection_id": inspection_id}
        )

    # ── persistence ────────────────────────────────────────────────────────
    def _model_version(self, extra: str = "") -> str:
        p = get_prompt("judgment")
        return f"{self.settings.rm_judgment_model}@{p.ref}{extra}"

    def _checks_json(
        self, checks: tuple[Check, ...], model_latency_ms: int, det_ms: int, rv: str
    ) -> list[dict[str, Any]]:
        qg = f"deterministic@quality-gate-{load_thresholds().version}"
        out = []
        for c in checks:
            if c.source == "model":
                version, latency = self._model_version(), model_latency_ms
            else:
                version = qg if c.check_key == "photo_quality" else f"deterministic@{rv}"
                latency = det_ms
            out.append(
                {
                    "check_key": c.check_key,
                    "verdict": c.verdict,
                    "confidence_bp": c.confidence_bp,
                    "detail": c.detail,
                    "model_version": version,
                    "latency_ms": latency,
                }
            )
        return out

    async def _insert_run(
        self,
        conn: Any,
        job: JobRecord,
        inspection_id: str,
        bundle: ContextBundle | None,
        trace: SessionTrace | None,
        *,
        status: str,
        started: float,
        output: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        config_version: str | None = None,
        skip_reasons: list[str] | None = None,
        error_class: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        prompt = get_prompt("judgment")
        manifest = dict(bundle.manifest) if bundle else {}
        if config_version:
            manifest["inspection_config_version"] = config_version
        # §13.1 / evidence hash clarity: record hash methods so verifiers can reproduce.
        manifest["hash_methods"] = {
            "output_sha256": OUTPUT_HASH_METHOD,
            "output_sha256_spec": OUTPUT_HASH_DESCRIPTION,
            "evidence_sha256": EVIDENCE_HASH_METHOD,
            "evidence_sha256_spec": EVIDENCE_HASH_DESCRIPTION,
        }
        await conn.execute(
            """INSERT INTO rm.inspection_runs (inspection_id, org_id, return_id, job_id, kind, model_id,
                 effort,
                 output_mode, prompt_id, prompt_version, prompt_sha256, judgment_schema_version,
                 context_manifest,
                 started_at, completed_at, status, skip_reasons, api_requests, tool_calls, usage,
                 cost_usd_micros,
                 latency_ms, provider_interaction_ids, finish_reasons, error_class, error_detail, output,
                 output_sha256, validation_report)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, to_timestamp(%s),
               now(), %s, %s,
                 %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)""",
            (
                inspection_id,
                job.org_id,
                job.return_id,
                job.job_id,
                job.kind,
                self.settings.rm_judgment_model if trace else None,
                self.settings.rm_judgment_thinking if trace else None,
                self.settings.rm_output_mode if trace else None,
                prompt.prompt_id,
                prompt.version,
                prompt.sha256,
                SCHEMA_VERSION,
                _json(manifest),
                started,
                status,
                skip_reasons,
                trace.requests_sent if trace else 0,
                len(trace.tools) if trace else 0,
                _json(trace.usage if trace else {}),
                trace.cost_usd_micros if trace else None,
                trace.latency_ms if trace else None,
                trace.interaction_ids if trace else [],
                trace.statuses if trace else [],
                error_class,
                error_detail,
                _json(output) if output is not None else None,
                _output_sha256(output) if output is not None else None,
                _json(validation) if validation is not None else None,
            ),
        )

    async def _persist_failed_run(
        self, job: JobRecord, inspection_id: str, bundle: ContextBundle, trace: SessionTrace, cause: Exception
    ) -> None:
        from returns_manager.jobs.retry import classify_error

        c = classify_error(cause)
        async with self.db.transaction(job.org_id) as conn:
            await self._insert_run(
                conn,
                job,
                inspection_id,
                bundle,
                trace,
                status="failed",
                started=time.time(),
                error_class=c.error_class,
                error_detail=c.detail[:500],
            )

    async def _insert_result(
        self,
        conn: Any,
        job: JobRecord,
        inspection_id: str,
        r: PipelineResult,
        trace: SessionTrace,
        det_ms: int,
        rv: str,
    ) -> None:
        d = r.decision
        await conn.execute(
            """INSERT INTO rm.inspection_results (result_id, org_id, return_id, inspection_id, identity_match,
                 fused_identity, unit_presence, completeness_status, components, cosmetic_grade,
                 amazon_condition,
                 listing_blockers, condition, model_observed_state, claim_signals, uncertainties,
                 retake_requests,
                 validator_actions, checks, escalation_state, recommended_disposition,
                 no_recommendation_reason,
                 provisional, relistable_as_is, disposition, disposition_inputs, requires_review,
                 review_reasons,
                 requires_signoff)
               VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s, %s::jsonb,
                 %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                 %s, %s, %s)""",
            (
                new_id(),
                job.org_id,
                job.return_id,
                inspection_id,
                r.identity.identity_match,
                _json(r.identity),
                r.presence.status,
                r.completeness.status,
                _json(r.completeness),
                r.condition.cosmetic_grade,
                r.condition.amazon_condition,
                list(r.condition.listing_blockers),
                _json(r.condition),
                r.judgment.model_observed_state,
                _json(r.claims),
                _json([u.model_dump() for u in r.judgment.uncertainties]),
                _json([x.model_dump() for x in r.judgment.retake_requests]),
                _json([dataclasses.asdict(a) for a in r.report.actions]),
                _json(self._checks_json(r.checks, trace.latency_ms, det_ms, rv)),
                "triggered_not_run" if r.escalation_triggers else "not_triggered",
                d.recommended_disposition,
                d.no_recommendation_reason,
                d.provisional,
                r.condition.relistable_as_is,
                _json({**dataclasses.asdict(d), "escalation_triggers": list(r.escalation_triggers)}),
                _json(r.inputs.canonical()),
                r.requires_review,
                list(r.review_reasons),
                d.requires_signoff,
            ),
        )

    def _skipped(
        self,
        job: JobRecord,
        facts: GateFacts,
        missing: MissingReference,
        auto: bool,
        unit_id: str | None = None,
    ) -> HandlerResult:
        """§11.2a: no model call; awaiting_review with the reason codes; every model check UNCERTAIN."""
        inspection_id = new_id()
        started = time.time()
        rv = rules_version(load_params())
        reason = missing.reasons[0]
        inputs = DispositionInputs(
            inspection_state="skipped",
            skip_reason=reason,
            usable_photo_count=facts.gate.non_fail_photos,
            unit_presence="uncertain",
            identity="uncertain",
            actual_sku=None,
            completeness_status="uncertain",
            essential_missing=(),
            nonessential_missing=(),
            essential_uncertain=(),
            nonessential_uncertain=(),
            cosmetic_grade=None,
            listing_blockers=(),
            blockers_undetermined=(),
            max_severity="none",
            new_only=False,
            opened_item_route="liquidate",
            damaged_item_route="dispose",
            list_price_minor=0,
            currency="INR",
            recovery_rate_bp=(),
            refurbish_cost_minor=0,
            restock_used_grades=(),
            refurbish_min_net_gain_minor=0,
            dispose_max_salvage_minor=0,
            high_value_threshold_minor=0,
            auto_disposition_enabled=auto,
        )
        decision = decide(inputs, rv)
        why = f"Inspection skipped ({', '.join(missing.reasons)}): missing {'; '.join(missing.missing)}."[
            :400
        ]
        gate = facts.gate
        checks = [
            {
                "check_key": "photo_quality",
                "verdict": "PASS" if gate.non_fail_photos >= 2 else "UNCERTAIN",
                "confidence_bp": 10000,
                "detail": f"{gate.non_fail_photos} photos passed the quality gate.",
                "model_version": f"deterministic@quality-gate-{load_thresholds().version}",
                "latency_ms": 0,
            },
            *[
                {
                    "check_key": k,
                    "verdict": "UNCERTAIN",
                    "confidence_bp": 0,
                    "detail": why,
                    "model_version": "not_run",
                    "latency_ms": 0,
                }
                for k in (
                    "unit_presence",
                    "identity",
                    "completeness",
                    "condition_grade",
                    "relistable_as_is",
                    "category_policy",
                )
            ],
        ]

        _unit_id: str = unit_id if unit_id is not None else job.return_id

        async def persist(conn: Any) -> None:
            await self._insert_run(
                conn,
                job,
                inspection_id,
                None,
                None,
                status="skipped",
                started=started,
                skip_reasons=missing.reasons,
            )
            await conn.execute(
                """INSERT INTO rm.inspection_results (result_id, org_id, return_id, inspection_id,
                     identity_match,
                     fused_identity, unit_presence, completeness_status, components, amazon_condition,
                     condition,
                     claim_signals, uncertainties, retake_requests, validator_actions, checks,
                     escalation_state,
                     no_recommendation_reason, provisional, disposition, disposition_inputs, requires_review,
                     review_reasons, requires_signoff)
                   VALUES (%s, %s, %s, %s, 'uncertain', %s::jsonb, 'uncertain', 'uncertain', '[]'::jsonb,
                     'uncertain', %s::jsonb, %s::jsonb, %s::jsonb, '[]'::jsonb, '[]'::jsonb, %s::jsonb,
                     'not_triggered', %s, false, %s::jsonb, %s::jsonb, true, %s, false)""",
                (
                    new_id(),
                    job.org_id,
                    job.return_id,
                    inspection_id,
                    _json({"skipped": missing.reasons}),
                    _json({"skipped": missing.reasons}),
                    _json(
                        {
                            "item_not_returned": "uncertain",
                            "wrong_item_returned": "uncertain",
                            "returned_damaged": "uncertain",
                        }
                    ),
                    _json([{"area": "identity", "reason": "reference_insufficient", "detail": why[:200]}]),
                    _json(checks),
                    decision.no_recommendation_reason,
                    _json(dataclasses.asdict(decision)),
                    _json(inputs.canonical()),
                    list(dict.fromkeys([*missing.reasons, *decision.review_reasons])),
                ),
            )
            # ── P7: chain events (in the same transaction) ──────────────────
            _actor = "system"
            await append_event(
                conn,
                org_id=job.org_id,
                unit_id=_unit_id,
                return_id=job.return_id,
                event_type=ET.INSPECTION_STARTED,
                actor_type=_actor,
                actor_id=f"worker/{job.job_id}",
                payload={"inspection_id": inspection_id, "job_id": job.job_id, "kind": job.kind},
            )
            await append_event(
                conn,
                org_id=job.org_id,
                unit_id=_unit_id,
                return_id=job.return_id,
                event_type=ET.INSPECTION_SKIPPED,
                actor_type=_actor,
                actor_id=f"worker/{job.job_id}",
                payload={
                    "inspection_id": inspection_id,
                    "skip_reasons": list(missing.reasons),
                    "missing": list(missing.missing),
                },
            )

        return HandlerResult(
            target_return_status=ReturnStatus.AWAITING_REVIEW,
            persist=persist,
            details={"inspection_id": inspection_id, "skipped": missing.reasons, "missing": missing.missing},
        )
