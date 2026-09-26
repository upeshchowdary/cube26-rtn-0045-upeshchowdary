# ADR-010 Explainer Agent architecture and evidence citation validator
Status: accepted
Owner: upeshchowdary
Date: 2026-09-26
Revisit by: 2026-12-01
Reversibility: reversible — the explainer is a read-only service that does not alter data models or database schemas

## Decision (one paragraph: what)

The Explainer Agent (§11.14) provides natural-language Q&A regarding why specific return decisions were made for units within the caller's organization. Exposed via `POST /api/v1/units/{unit_id}/explain` and the MCP tool `explain_return_decision`, it operates in a strictly read-only mode using `gemini-3.1-flash-lite` (with low thinking) under a separate daily request quota (`RM_DAILY_REQUEST_BUDGET_EXPLAINER`). Context is strictly assembled from the stored evidence record, hash-chained events, active rule definitions, condition rubric texts, and human overrides. The output is structured JSON containing `{answer, citations: [{kind, ref}], not_recorded}`. Crucially, a programmatic Citation Validator checks every cited reference against the assembled unit context; if an answer produces zero valid citations, the answer is replaced by the deterministic fallback: *"This is not recorded in the evidence for this unit."* The Explainer Agent is explicitly forbidden from generating new verdicts, altering grades, or changing dispositions.

## Why

- **Hallucination Prevention**: LLMs tend to invent plausible-sounding justifications when questioned about complex decisions. Enforcing programmatic resolution of citations against immutable database records guarantees that only factual evidence is communicated to operators and auditors.
- **Quota Separation**: Explainer interactions use the cheaper, faster `gemini-3.1-flash-lite` model with dedicated quota so operator inquiries never deplete the primary inspection judgment budget.
- **Separation of Concerns**: Explanations provide visibility into past determinations without risking accidental mutation of finalized contracts.

## Rejected alternatives (and why)

- **Free-form conversational chat without structured citations**: Susceptible to hallucinations and unverified claims regarding missing items or condition grades.
- **Using the primary judgment model (`gemini-3.8-flash`)**: Unnecessarily expensive and risks exhausting scarce intake quota on read-only queries.
- **Dynamic SQL/vector tool execution by the model**: Introduces prompt injection risks and potential tenant data leakage; deterministic pre-assembled context provides strict tenant isolation.

## Consequences

- If the model references a field or event that does not exist in the record, the validator strips the citation; if no valid citations remain, the response fails safe with an honest "not recorded" notice.
- Responses conform strictly to the forbidden language rules (§24), describing only observed facts and recorded rules.
