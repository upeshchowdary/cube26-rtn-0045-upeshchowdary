# ADR-009 Webhooks delivery, payload structure, and HMAC signatures
Status: accepted
Owner: upeshchowdary
Date: 2026-09-26
Revisit by: 2026-12-01
Reversibility: reversible — webhook payload versioning and signature schemes are forward-compatible

## Decision (one paragraph: what)

Outbound webhook notifications are dispatched on evidence lifecycle events (`evidence.finalized` and `evidence.superseded`) to notify downstream consumer systems (e.g. Recovery Manager, Inventory, Billing). Payloads are lightweight notification envelopes containing `{event, contract_version, org_id, unit_id, record_id, record_version, document_sha256, links}` rather than full bulky inspection documents; consumers fetch detailed evidence using authenticated GET requests. Every outbound HTTP POST request includes an anti-replay authentication header `RM-Signature: t=<unix_timestamp>,v1=<hex_hmac>` computed via HMAC-SHA256 over `t + "." + raw_body` using the endpoint's pre-shared secret. Receivers enforce a maximum 5-minute clock drift window. All destination URLs are validated against `RM_WEBHOOK_ALLOWLIST` (allowing localhost/test endpoints in dev environments) to prevent server-side request forgery (SSRF).

## Why

- **Minimal Attack Surface & Reduced Egress**: Lightweight event envelopes eliminate sensitive photographic and full text egress across untrusted webhook listeners; consumers pull full records under their scoped credentials.
- **Cryptographic Authenticity & Anti-Replay**: The HMAC-SHA256 signature with an explicit timestamp header prevents tampering in transit and defeats replay attacks.
- **SSRF Defense**: The explicit hostname/URL allowlist blocks malicious operators or injected webhook registrations from scanning private internal infrastructure or cloud metadata endpoints (`169.254.169.254`).

## Rejected alternatives (and why)

- **Embedding full evidence records inside webhook bodies**: Increases network egress, risks leaking detailed tenant images and inspection notes, and complicates signing of large payloads.
- **Unsigned HTTP callbacks**: Leaves downstream systems vulnerable to spoofed finalization notifications and false restock triggers.
- **JWT tokens in webhook headers**: Unnecessarily complex compared to standard HMAC-SHA256 webhook signatures (Stripe/GitHub style) which are universally supported by webhook receivers.

## Consequences

- Webhook subscriptions and delivery attempt records are tracked with status, response codes, and exponential backoff retry scheduling.
- The webhook dispatcher operates asynchronously, ensuring that return submission and inspection pipelines are never blocked by slow webhook endpoints.
