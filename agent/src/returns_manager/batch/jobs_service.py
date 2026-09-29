"""Filesystem-backed batch-upload jobs (§15 API surface, batch/ pipeline underneath).

Upload a before/returned CSV pair, run the real standalone batch pipeline
(`batch/runner.py:run_batch` - the exact code path `returns-manager batch process` uses,
including real Gemini calls) against it in the background, and let the caller poll status,
read the resulting rows, download the output CSV, or delete the job and its files.

Deliberately NOT backed by `rm.inspection_jobs` (the real durable DB job queue used by the
worker/API elsewhere in this codebase) - this reuses the standalone batch tool's own
no-database design on purpose, so a batch upload never touches Postgres. Tenancy is still
enforced: every job lives under `<root>/<org_id>/<job_id>/`, keyed by the authenticated
caller's own `org_id`, so one org can never list, read or delete another org's upload -
even though the isolation here is a filesystem path, not an RLS policy. `--confirm-spend`-
style intent (§ CLAUDE.md "Spend guards") is required explicitly by the route layer before
a job is ever created; this service does not decide that on its own.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import shutil
import time
from dataclasses import asdict, dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any, Literal

from returns_manager.batch.runner import run_batch
from returns_manager.config import Settings
from returns_manager.disposition.engine import Route
from returns_manager.ids import new_id
from returns_manager.llm.client import ModelClient
from returns_manager.security.roles import Forbidden

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "processing", "done", "failed"]
DecisionAction = Literal["accept", "override", "retake_request", "review_request"]


@dataclass
class BatchJob:
    job_id: str
    org_id: str
    status: JobStatus
    created_at: float
    before_filename: str
    returned_filename: str
    total_rows: int = 0
    processed: int = 0
    uncertain: int = 0
    live_requests: int = 0
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    created_by: str = ""  # actor label of the uploader; the four-eyes check compares against it


class BatchJobsService:
    def __init__(self, root: Path, settings: Settings, client: ModelClient) -> None:
        self.root = root
        self.settings = settings
        self.client = client
        self._jobs: dict[str, BatchJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def _org_dir(self, org_id: str) -> Path:
        d = self.root / org_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _job_dir(self, org_id: str, job_id: str) -> Path:
        return self._org_dir(org_id) / job_id

    def _meta_path(self, job: BatchJob) -> Path:
        return self._job_dir(job.org_id, job.job_id) / "meta.json"

    def _load_existing(self) -> None:
        for meta_path in self.root.glob("*/*/meta.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                job = BatchJob(**data)
            except Exception:
                logger.warning("skipping unreadable batch job metadata at %s", meta_path, exc_info=True)
                continue
            # A job left "processing" across a server restart can never finish -
            # surface that honestly instead of showing a stuck spinner forever.
            if job.status == "processing":
                job.status = "failed"
                job.error = "server restarted while this job was running"
            self._jobs[job.job_id] = job

    def _save(self, job: BatchJob) -> None:
        self._meta_path(job).write_text(json.dumps(asdict(job)), encoding="utf-8")

    def list_jobs(self, org_id: str) -> list[BatchJob]:
        return sorted(
            (j for j in self._jobs.values() if j.org_id == org_id),
            key=lambda j: j.created_at,
            reverse=True,
        )

    def get_job(self, org_id: str, job_id: str) -> BatchJob | None:
        job = self._jobs.get(job_id)
        return job if job is not None and job.org_id == org_id else None

    async def create_job(
        self,
        *,
        org_id: str,
        before_bytes: bytes,
        before_filename: str,
        returned_bytes: bytes,
        returned_filename: str,
        default_category: str | None,
        max_requests: int,
        created_by: str = "",
    ) -> BatchJob:
        job_id = new_id()
        job_dir = self._job_dir(org_id, job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "before.csv").write_bytes(before_bytes)
        (job_dir / "returned.csv").write_bytes(returned_bytes)

        returned_row_count = max(0, returned_bytes.decode("utf-8", errors="ignore").count("\n") - 1)
        job = BatchJob(
            job_id=job_id,
            org_id=org_id,
            status="queued",
            created_at=time.time(),
            before_filename=before_filename,
            returned_filename=returned_filename,
            total_rows=returned_row_count,
            created_by=created_by,
        )
        self._jobs[job_id] = job
        self._save(job)
        self._tasks[job_id] = asyncio.create_task(self._run(job, default_category, max_requests))
        return job

    async def _run(self, job: BatchJob, default_category: str | None, max_requests: int) -> None:
        job.status = "processing"
        self._save(job)
        job_dir = self._job_dir(job.org_id, job.job_id)

        def _on_progress(
            row_out: Any,
            det: Any,
            summary: Any,
            current_rows: list[dict[str, str]],
            current_details: dict[str, Any],
        ) -> None:
            from returns_manager.batch.io_csv import write_output_csv

            job.processed = summary.processed
            job.uncertain = summary.uncertain
            job.live_requests = summary.live_requests
            try:
                write_output_csv(job_dir / "output.csv", current_rows)
                (job_dir / "rows_detail.json").write_text(json.dumps(current_details), encoding="utf-8")
                self._save(job)
            except (OSError, TypeError, ValueError):  # a partial-progress write failing must not stop the run
                logger.warning("could not write progress for batch job %s", job.job_id, exc_info=True)

        try:
            rows, details_by_record_id, summary = await run_batch(
                before_path=job_dir / "before.csv",
                returned_path=job_dir / "returned.csv",
                settings=self.settings,
                client=self.client,
                default_category=default_category,
                max_requests=max_requests,
                on_progress=_on_progress,
            )
            from returns_manager.batch.io_csv import write_output_csv

            write_output_csv(job_dir / "output.csv", rows)
            (job_dir / "rows_detail.json").write_text(json.dumps(details_by_record_id), encoding="utf-8")
            job.status = "done"
            job.total_rows = summary.total_rows
            job.processed = summary.processed
            job.uncertain = summary.uncertain
            job.live_requests = summary.live_requests
            job.notes = summary.notes
        except Exception as exc:  # fail open: the job record itself must not vanish
            job.status = "failed"
            job.error = str(exc)
        self._save(job)

    def delete_job(self, org_id: str, job_id: str) -> bool:
        job = self.get_job(org_id, job_id)
        if job is None:
            return False
        task = self._tasks.pop(job_id, None)
        if task is not None and not task.done():
            task.cancel()
        shutil.rmtree(self._job_dir(org_id, job_id), ignore_errors=True)
        self._jobs.pop(job_id, None)
        return True

    def clear_all_jobs(self, org_id: str) -> int:
        jobs = [j for j in list(self._jobs.values()) if j.org_id == org_id]
        count = 0
        for j in jobs:
            if self.delete_job(org_id, j.job_id):
                count += 1
        return count

    def output_path(self, org_id: str, job_id: str) -> Path | None:
        job = self.get_job(org_id, job_id)
        if job is None:
            return None
        path = self._job_dir(org_id, job_id) / "output.csv"
        return path if path.exists() else None

    def output_rows(self, org_id: str, job_id: str) -> list[dict[str, str]] | None:
        """The run's output rows exactly as written - never recomputed or filled in on read."""
        path = self.output_path(org_id, job_id)
        if path is None:
            return None
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _detail_path(self, org_id: str, job_id: str) -> Path:
        return self._job_dir(org_id, job_id) / "rows_detail.json"

    def _decisions_path(self, org_id: str, job_id: str) -> Path:
        return self._job_dir(org_id, job_id) / "decisions.json"

    def output_row_detail(self, org_id: str, job_id: str, record_id: str) -> dict[str, Any] | None:
        """The rich per-row detail (§14.2 checks, identity, completeness, condition, decision,
        raw judgment) for one row of a batch job - see `runner._build_row_detail`. Only rows that
        got a real model response run through the pipeline have one; a fail-open row has none, and
        nothing is synthesized in its place."""
        job = self.get_job(org_id, job_id)
        if job is None:
            return None
        path = self._detail_path(org_id, job_id)
        if not path.exists():
            return None
        try:
            all_detail: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("unreadable rows_detail.json for job %s", job_id, exc_info=True)
            return None
        detail = all_detail.get(record_id)
        return detail if isinstance(detail, dict) and detail else None

    def row_requires_signoff(self, org_id: str, job_id: str, record_id: str) -> bool:
        """Whether the engine's decision for this row needs a second person's sign-off (S01 dispose,
        S02 high value). A row with no detail has no engine decision to sign off."""
        detail = self.output_row_detail(org_id, job_id, record_id)
        return bool(detail and detail.get("decision", {}).get("requires_signoff"))

    def _load_decisions(self, org_id: str, job_id: str) -> list[dict[str, Any]]:
        path = self._decisions_path(org_id, job_id)
        if not path.exists():
            return []
        return list(json.loads(path.read_text(encoding="utf-8")))

    def get_decisions(self, org_id: str, job_id: str, record_id: str) -> list[dict[str, Any]] | None:
        """Chronological (oldest first) decision history for one row. `None` if the job doesn't
        exist or isn't this org's; an empty list is a real, valid answer (no decision recorded
        yet), so the two are distinguished."""
        job = self.get_job(org_id, job_id)
        if job is None:
            return None
        return [d for d in self._load_decisions(org_id, job_id) if d.get("record_id") == record_id]

    def record_decision(
        self,
        org_id: str,
        job_id: str,
        record_id: str,
        *,
        action: DecisionAction,
        new_disposition: Route | None,
        reason: str,
        actor: str,
    ) -> dict[str, Any] | None:
        """Appends one decision to the job's append-only `decisions.json` - never rewrites or
        removes an earlier entry, so the full history is always reconstructable. Returns the
        recorded entry, or `None` if the job doesn't exist / isn't this org's (the route maps
        that to 404)."""
        job = self.get_job(org_id, job_id)
        if job is None:
            return None
        if (
            action in ("accept", "override")
            and job.created_by
            and actor == job.created_by
            and self.row_requires_signoff(org_id, job_id, record_id)
        ):
            # Four-eyes (§12.2 S01/S02, review/service.py): whoever submitted the returns cannot
            # also sign off a disposition that requires sign-off.
            raise Forbidden("four-eyes rule: the uploader of this batch cannot sign off this row")
        entry: dict[str, Any] = {
            "record_id": record_id,
            "action": action,
            "new_disposition": new_disposition,
            "reason": reason,
            "actor": actor,
            "at": time.time(),
        }
        all_decisions = self._load_decisions(org_id, job_id)
        all_decisions.append(entry)
        self._decisions_path(org_id, job_id).write_text(json.dumps(all_decisions), encoding="utf-8")

        # Synchronize output.csv directly with the approved / overridden disposition
        output_p = self._job_dir(org_id, job_id) / "output.csv"
        if output_p.exists():
            from returns_manager.batch.io_csv import write_output_csv

            rows = self.output_rows(org_id, job_id) or []
            updated = False
            for r in rows:
                if r.get("record_id") == record_id:
                    if action == "override" and new_disposition:
                        r["operator_disposition"] = new_disposition
                        updated = True
                    elif action == "accept":
                        if new_disposition:
                            r["operator_disposition"] = new_disposition
                            updated = True
                        elif r.get("operator_disposition") == "pending_review":
                            detail = self.output_row_detail(org_id, job_id, record_id)
                            rec = (
                                detail.get("decision", {}).get("recommended_disposition") if detail else None
                            )
                            if rec and rec != "pending_review":
                                r["operator_disposition"] = rec
                                updated = True
                    elif action == "review_request":
                        r["operator_disposition"] = "pending_review"
                        updated = True
            if updated:
                write_output_csv(output_p, rows)

        return entry

    def render_output_csv(self, org_id: str, job_id: str) -> bytes | None:
        """The downloadable output CSV, with `operator_disposition` on each row updated to
        reflect the latest `override` decision recorded for that row (chronological order; an
        `accept` confirms the engine's own route and changes nothing). The stored `output.csv`
        itself is never rewritten - this renders a fresh copy at request time, so it always
        reflects the current decision history."""
        from returns_manager.batch.io_csv import OUTPUT_FIELDNAMES

        rows = self.output_rows(org_id, job_id)
        if rows is None:
            return None
        all_decisions = self._load_decisions(org_id, job_id)
        by_record: dict[str, list[dict[str, Any]]] = {}
        for decision in all_decisions:
            by_record.setdefault(decision["record_id"], []).append(decision)

        buf = StringIO()
        writer = csv.DictWriter(buf, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            disposition = row.get("operator_disposition", "")
            for decision in by_record.get(row.get("record_id", ""), []):
                if decision["action"] in ("override", "accept") and decision.get("new_disposition"):
                    disposition = decision["new_disposition"]
                elif decision["action"] == "review_request":
                    disposition = "pending_review"
            out_row = dict(row)
            out_row["operator_disposition"] = disposition
            writer.writerow({k: out_row.get(k, "") for k in OUTPUT_FIELDNAMES})
        return buf.getvalue().encode("utf-8")
