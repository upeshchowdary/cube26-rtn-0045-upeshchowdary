-- 0011 · Webhook subscriptions and delivery records, persisted (§17).
--
-- P14 originally kept webhook subscriptions in a process-local in-memory dict behind a
-- module-level singleton. That is broken in this project's real deployment: the API
-- server and the worker are separate OS processes (`returns-manager api serve` vs
-- `returns-manager worker`), each with its own singleton, so a subscription registered
-- through the REST API was invisible to the worker process that actually dispatches
-- `evidence.finalized`/`evidence.superseded` on record finalization - webhooks never
-- fired. This migration gives subscriptions and delivery history a durable, tenant-
-- isolated home so any process can read the same subscription list.
SET LOCAL ROLE rm_owner;

CREATE TABLE rm.webhook_subscriptions (
  subscription_id text PRIMARY KEY,
  org_id          text NOT NULL CHECK (org_id <> ''),
  url             text NOT NULL CHECK (url <> ''),
  secret          text NOT NULL CHECK (length(secret) >= 16),
  events          text[] NOT NULL DEFAULT '{evidence.finalized,evidence.superseded}',
  is_active       boolean NOT NULL DEFAULT true,
  created_by      text NOT NULL CHECK (created_by <> ''),
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, subscription_id),  -- target of the composite FK below
  FOREIGN KEY (org_id) REFERENCES rm.organizations (org_id)
);
CREATE INDEX webhook_subscriptions_org_active ON rm.webhook_subscriptions (org_id) WHERE is_active;

CREATE TABLE rm.webhook_deliveries (
  delivery_id     text PRIMARY KEY,
  org_id          text NOT NULL CHECK (org_id <> ''),
  subscription_id text NOT NULL,
  event           text NOT NULL,
  unit_id         text NOT NULL,
  url             text NOT NULL,
  status_code     integer,
  success         boolean NOT NULL DEFAULT false,
  duration_ms     numeric,
  error           text,
  attempt         integer NOT NULL DEFAULT 1 CHECK (attempt >= 1),
  next_retry_at   timestamptz,               -- backoff up to 24h (§17); null once given up or delivered
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (org_id, subscription_id) REFERENCES rm.webhook_subscriptions (org_id, subscription_id)
);
CREATE INDEX webhook_deliveries_org_sub ON rm.webhook_deliveries (org_id, subscription_id, created_at);
CREATE INDEX webhook_deliveries_retry_due
  ON rm.webhook_deliveries (next_retry_at)
  WHERE next_retry_at IS NOT NULL;

-- ── Row-level security ───────────────────────────────────────────────────────
ALTER TABLE rm.webhook_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.webhook_subscriptions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.webhook_subscriptions
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.webhook_deliveries FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.webhook_deliveries
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

-- UPDATE on subscriptions is needed for soft-delete (is_active = false); deliveries are
-- append-only like every other evidence/audit table in this schema (no UPDATE, no DELETE).
GRANT SELECT, INSERT, UPDATE ON rm.webhook_subscriptions TO rm_app;
GRANT SELECT, INSERT ON rm.webhook_deliveries TO rm_app;
