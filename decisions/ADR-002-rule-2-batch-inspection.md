# ADR-002 Rule-2 interpretation (single-session batched inspection)
Status: accepted
Owner: upeshchowdary
Date: 2026-09-25
Revisit by: 2026-11-01
Reversibility: irreversible — splitting inspection into per-check calls violates core engineering rules and budget limits

## Decision (one paragraph: what)

One inspection of a returned unit constitutes exactly **one Judgment session**. That single session evaluates all inspection checks simultaneously (unit presence, identity, completeness per component, condition grade, observed state, and retake requirements) in a single structured JSON response. There is never an API request per check. In normal operation, an inspection consumes exactly one API request against Google Gemini Developer API. When visual ambiguity arises, the model may execute at most one tool round trip from an exception-only allowlist (crop region, fetch additional reference views, or fetch a sibling SKU), capped at `RM_MAX_ROUND_TRIPS` (default 2). Escalation and blind audit are executed as full, independent re-judgments rather than per-check calls. Average API requests per inspection are tracked as a measured metric with a target mean ≤ 1.2 requests/inspection.

## Why

- **Resource Scarcity on Free Tier**: Google Gemini free-tier keys enforce daily request caps (approximately 20 requests/day on standard models) and rate limits (15 RPM). Multi-call per-check architectures exhaust quota after only a few returned units.
- **Holistic Multimodal Reasoning**: Evaluating packaging, labels, completeness, and surface wear in a single context window allows cross-feature validation (e.g. box-swap detection where outer packaging matches but internal device is mismatched).
- **Latency & Predictable Cost**: Minimizing network round trips bounds inspection duration to sub-5-second processing times and avoids compounding network failures.

## Rejected alternatives (and why)

- **Dedicated check per model call (sequential agent chain)**: Consumes 4–6 API requests per returned unit, instantly exhausting free-tier daily quotas and multiplying p95 latency.
- **Parallel check calls (async scatter-gather)**: Triggers upstream 429 rate limit errors (RPM limit) and prevents cross-check contextual coherence.
- **Forced tool calls**: Mandating tool calls consumes extra requests unnecessarily when primary photos are clear and decisive.

## Consequences

- Prompts and schemas must provide complete context pre-assembled before the initial call.
- Tool use is strictly configured as `tool_choice="auto"`.
- Requests per inspection, tokens, and tool calls are captured and reported in observability views.
