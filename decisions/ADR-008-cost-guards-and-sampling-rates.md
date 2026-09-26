# ADR-008 Cost guards, quota management, and sampling rates
Status: accepted
Owner: upeshchowdary
Date: 2026-09-25
Revisit by: 2026-11-01
Reversibility: reversible — parameters can be adjusted via environment configuration

## Decision (one paragraph: what)

The backend operates strictly under a zero-dollar ($0.00) paid model spend constraint by utilizing the Google Gemini Developer API free tier. Request volumes are enforced through an in-process daily request-quota guard (`llm/quota.py`) per model role (`judgment`, `escalation`, `audit`, `explainer`) with fixed default ceilings (18 requests/day for judgment, 18 for audit, 50 for explainer) that reset at Pacific midnight in accordance with Google AI Studio reset timing. In normal development and testing, all LLM interactions are served via pre-recorded replay cassettes; unit tests are forbidden from making live external API calls. Bulk operations (load testing, eval runs) require explicit confirmation flags (`--confirm-spend`) and run preflight checks (`observability/spend_guard.py`) before firing requests. Audit sampling is configured to 0.0 in normal operations to conserve quota and 1.0 (100%) during eval runs against an independent free model (`gemini-3.6-flash`).

## Why

- **Unintended Spend Prevention**: Without rigid preflight spend guards, automated background tasks or load testing scripts could incur unexpected billing if a billing-enabled API key were configured.
- **Quota Starvation Defense**: The free tier imposes hard daily ceilings; unthrottled requests would exhaust quota within minutes, blocking operators from inspecting units for the remainder of the day.
- **Reproducibility**: Replay cassettes ensure deterministic and fast CI runs without network dependency or quota consumption.

## Rejected alternatives (and why)

- **Pay-as-you-go billing with API spend limits**: Project constraints stipulate free-tier operation without payment cards attached.
- **Uniform quota across all roles**: A single shared pool allows background audit or explainer queries to starve critical intake inspections. Per-role quotas isolate operational judgment capacity.
- **Continuous 10% audit sampling in dev**: Consumes limited daily requests on auxiliary validation rather than primary inspection workflows.

## Consequences

- When daily quota is exhausted, incoming jobs transition gracefully to `PENDING` with retry backoff until Pacific midnight reset, never dropping units or failing closed abruptly.
- Live operations fail early with exit code 4 (`SpendGuardRefused`) unless explicitly approved by the operator.
