-- 0008 · Evidence integrity: unit event chain, org ledger, evidence records (§13).
-- Tenant tables: RLS enabled and forced. All tables are append-only (no DELETE, no UPDATE on immutable columns).
SET LOCAL ROLE rm_owner;

-- ─────────────────────────────────────────────────────────────────────────────
-- Per-unit chain heads: one row per (org_id, unit_id); updated in the same
-- transaction as the INSERT into unit_events (FOR UPDATE on this row serialises
-- all events for the same unit).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE rm.unit_chain_heads (
  org_id         text NOT NULL CHECK (org_id <> ''),
  unit_id        text NOT NULL CHECK (unit_id <> ''),
  last_seq       integer NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
  last_event_id  text,
  last_hash      text NOT NULL CHECK (last_hash ~ '^[0-9a-f]{64}$'),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, unit_id)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Unit event chain: one row per event.
-- `payload_sha256` = SHA-256(JCS(payload)).
-- `event_hash`     = SHA-256(b"rm/evt/v1" || 0x00 || prev_event_hash_bytes || JCS(event_core))
-- Both are computed in Python before INSERT; the DB stores them for verification.
-- No floats in payload (basis points / minor units / strings).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE rm.unit_events (
  event_id         text PRIMARY KEY,
  org_id           text NOT NULL CHECK (org_id <> ''),
  unit_id          text NOT NULL CHECK (unit_id <> ''),
  return_id        text NOT NULL CHECK (return_id <> ''),
  seq              integer NOT NULL CHECK (seq >= 1),
  schema_version   text NOT NULL DEFAULT 'rm/evt/v1',
  event_type       text NOT NULL,
  occurred_at      timestamptz NOT NULL DEFAULT now(),
  actor_type       text NOT NULL CHECK (actor_type IN ('system', 'operator', 'model', 'api_client')),
  actor_id         text NOT NULL CHECK (actor_id <> ''),
  payload          jsonb NOT NULL,
  payload_sha256   text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  prev_event_hash  text NOT NULL CHECK (prev_event_hash ~ '^[0-9a-f]{64}$'),
  event_hash       text NOT NULL CHECK (event_hash ~ '^[0-9a-f]{64}$'),
  UNIQUE (org_id, unit_id, seq),            -- no forks: each seq is unique per unit
  UNIQUE (org_id, event_id),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id)
);
CREATE INDEX unit_events_unit ON rm.unit_events (org_id, unit_id, seq);

-- ─────────────────────────────────────────────────────────────────────────────
-- Org ledger heads: one row per org; updated alongside org_ledger INSERTs.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE rm.org_ledger_heads (
  org_id       text PRIMARY KEY CHECK (org_id <> ''),
  last_seq     integer NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
  last_hash    text NOT NULL CHECK (last_hash ~ '^[0-9a-f]{64}$'),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Org ledger: appended on record_finalized, record_superseded and system events
-- (control_changed, key_issued, key_revoked, circuit_opened, circuit_closed).
-- `ledger_hash` = SHA-256(b"rm/ledger/v1" || 0x00 || prev_ledger_hash_bytes || JCS(entry_core))
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE rm.org_ledger (
  entry_id            text PRIMARY KEY,
  org_id              text NOT NULL CHECK (org_id <> ''),
  seq                 integer NOT NULL CHECK (seq >= 1),
  entry_type          text NOT NULL CHECK (entry_type IN (
                        'record_finalized', 'record_superseded',
                        'control_changed', 'key_issued', 'key_revoked',
                        'circuit_opened', 'circuit_closed')),
  record_id           text,               -- non-NULL for record_finalized / record_superseded
  record_version      integer,
  document_sha256     text CHECK (document_sha256 IS NULL OR document_sha256 ~ '^[0-9a-f]{64}$'),
  unit_head_event_hash text CHECK (unit_head_event_hash IS NULL OR unit_head_event_hash ~ '^[0-9a-f]{64}$'),
  payload             jsonb NOT NULL,
  prev_ledger_hash    text NOT NULL CHECK (prev_ledger_hash ~ '^[0-9a-f]{64}$'),
  ledger_hash         text NOT NULL CHECK (ledger_hash ~ '^[0-9a-f]{64}$'),
  occurred_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, seq)
);
CREATE INDEX org_ledger_org ON rm.org_ledger (org_id, seq);

-- ─────────────────────────────────────────────────────────────────────────────
-- Evidence records (§13.7): written at finalization (v1) and on post-finalization
-- overrides (vN+1; previous row marked superseded=true, a ledger entry per time).
-- document_sha256 = SHA-256(JCS(document)) computed before INSERT.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE rm.evidence_records (
  evidence_id        text PRIMARY KEY,
  org_id             text NOT NULL CHECK (org_id <> ''),
  return_id          text NOT NULL,
  unit_id            text NOT NULL CHECK (unit_id <> ''),
  record_version     integer NOT NULL CHECK (record_version >= 1),
  document           jsonb NOT NULL,      -- full contract document; never thinking content
  document_sha256    text NOT NULL CHECK (document_sha256 ~ '^[0-9a-f]{64}$'),
  unit_head_event_hash text NOT NULL CHECK (unit_head_event_hash ~ '^[0-9a-f]{64}$'),
  status             text NOT NULL DEFAULT 'finalized' CHECK (status IN ('finalized', 'superseded')),
  finalized_at       timestamptz NOT NULL DEFAULT now(),
  superseded_at      timestamptz,
  superseded_by      text REFERENCES rm.evidence_records (evidence_id),
  UNIQUE (org_id, return_id, record_version),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id)
);
CREATE INDEX evidence_records_return ON rm.evidence_records (org_id, return_id);
CREATE INDEX evidence_records_unit ON rm.evidence_records (org_id, unit_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Row-level security on all four tables
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE rm.unit_chain_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.unit_chain_heads FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.unit_chain_heads
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.unit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.unit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.unit_events
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.org_ledger_heads ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.org_ledger_heads FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.org_ledger_heads
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.org_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.org_ledger FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.org_ledger
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.evidence_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.evidence_records FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.evidence_records
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

-- ─────────────────────────────────────────────────────────────────────────────
-- Grants
GRANT SELECT, INSERT ON rm.unit_events, rm.org_ledger TO rm_app;
GRANT SELECT, INSERT, UPDATE ON rm.unit_chain_heads, rm.org_ledger_heads, rm.evidence_records TO rm_app;

