-- 0009 · Human decisions, review resolution, sign-off, escalation merge and audit findings (§7.5, §11.12-13).
-- All tables are tenant-scoped. Human/model outputs are append-only: no decision is silently replaced.
SET LOCAL ROLE rm_owner;

CREATE TABLE rm.operator_decisions (
  decision_id text PRIMARY KEY,
  org_id text NOT NULL CHECK (org_id <> ''),
  return_id text NOT NULL,
  action text NOT NULL CHECK (action IN ('accept', 'override')),
  operator_id text NOT NULL CHECK (operator_id <> ''),
  note text,
  decided_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id)
);
CREATE INDEX operator_decisions_return ON rm.operator_decisions (org_id, return_id, decided_at);

CREATE TABLE rm.overrides (
  override_id text PRIMARY KEY,
  org_id text NOT NULL CHECK (org_id <> ''),
  return_id text NOT NULL,
  record_version integer,
  field_path text NOT NULL CHECK (field_path IN (
    'identity_match', 'unit_presence', 'cosmetic_grade', 'amazon_condition', 'disposition'
  ) OR field_path ~ '^component:[A-Za-z0-9._-]+\\.status$'),
  original_value jsonb NOT NULL,
  new_value jsonb NOT NULL,
  reason_code text NOT NULL CHECK (reason_code IN (
    'missed_defect', 'false_defect', 'occluded_component', 'similar_sku', 'packaging_state_misread',
    'barcode_misread', 'policy_exception', 'photo_quality', 'other'
  )),
  reason_text text NOT NULL CHECK (length(reason_text) BETWEEN 1 AND 1000),
  actor_id text NOT NULL CHECK (actor_id <> ''),
  actor_role text NOT NULL CHECK (actor_role IN ('operator', 'reviewer', 'admin')),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id)
);
CREATE INDEX overrides_return ON rm.overrides (org_id, return_id, created_at);

CREATE TABLE rm.review_resolutions (
  resolution_id text PRIMARY KEY,
  org_id text NOT NULL CHECK (org_id <> ''),
  return_id text NOT NULL,
  reviewer_id text NOT NULL CHECK (reviewer_id <> ''),
  resolution jsonb NOT NULL,
  note text,
  resolved_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id)
);
CREATE INDEX review_resolutions_return ON rm.review_resolutions (org_id, return_id, resolved_at);

CREATE TABLE rm.signoffs (
  signoff_id text PRIMARY KEY,
  org_id text NOT NULL CHECK (org_id <> ''),
  return_id text NOT NULL,
  decision text NOT NULL CHECK (decision IN ('approved', 'rejected')),
  reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 1000),
  actor_id text NOT NULL CHECK (actor_id <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id)
);

-- Derived effective state is separate from the immutable inspection result.  It makes a human action
-- reproducible without pretending that a model output was edited.
CREATE TABLE rm.human_decision_snapshots (
  snapshot_id text PRIMARY KEY,
  org_id text NOT NULL CHECK (org_id <> ''),
  return_id text NOT NULL,
  source_inspection_id text NOT NULL,
  action text NOT NULL CHECK (action IN ('accept', 'override', 'review_resolution', 'signoff')),
  effective_values jsonb NOT NULL,
  effective_disposition jsonb NOT NULL,
  unresolved_review_reasons text[] NOT NULL DEFAULT '{}',
  requires_signoff boolean NOT NULL,
  created_by text NOT NULL CHECK (created_by <> ''),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id),
  FOREIGN KEY (org_id, source_inspection_id) REFERENCES rm.inspection_runs (org_id, inspection_id)
);
CREATE INDEX human_decision_snapshots_return ON rm.human_decision_snapshots (org_id, return_id, created_at);

CREATE TABLE rm.escalation_merges (
  merge_id text PRIMARY KEY,
  org_id text NOT NULL CHECK (org_id <> ''),
  return_id text NOT NULL,
  primary_inspection_id text NOT NULL,
  escalation_inspection_id text NOT NULL,
  area text NOT NULL,
  primary_value jsonb NOT NULL,
  escalation_value jsonb NOT NULL,
  merged_value jsonb NOT NULL,
  outcome text NOT NULL CHECK (outcome IN ('resolved_by_escalation', 'kept_primary', 'model_disagreement', 'uncertain')),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id),
  FOREIGN KEY (org_id, primary_inspection_id) REFERENCES rm.inspection_runs (org_id, inspection_id),
  FOREIGN KEY (org_id, escalation_inspection_id) REFERENCES rm.inspection_runs (org_id, inspection_id),
  UNIQUE (org_id, primary_inspection_id, escalation_inspection_id, area)
);

CREATE TABLE rm.audit_findings (
  finding_id text PRIMARY KEY,
  org_id text NOT NULL CHECK (org_id <> ''),
  return_id text NOT NULL,
  primary_inspection_id text NOT NULL,
  audit_inspection_id text NOT NULL,
  disagreements text[] NOT NULL DEFAULT '{}',
  routes_to_review boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id),
  FOREIGN KEY (org_id, primary_inspection_id) REFERENCES rm.inspection_runs (org_id, inspection_id),
  FOREIGN KEY (org_id, audit_inspection_id) REFERENCES rm.inspection_runs (org_id, inspection_id),
  UNIQUE (org_id, primary_inspection_id, audit_inspection_id)
);

-- Tenant RLS is deliberately repeated per table: missing one table is a cross-org data leak.
ALTER TABLE rm.operator_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.operator_decisions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.operator_decisions USING (org_id = NULLIF(current_setting('app.org_id', true), '')) WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));
ALTER TABLE rm.overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.overrides FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.overrides USING (org_id = NULLIF(current_setting('app.org_id', true), '')) WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));
ALTER TABLE rm.review_resolutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.review_resolutions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.review_resolutions USING (org_id = NULLIF(current_setting('app.org_id', true), '')) WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));
ALTER TABLE rm.signoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.signoffs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.signoffs USING (org_id = NULLIF(current_setting('app.org_id', true), '')) WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));
ALTER TABLE rm.human_decision_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.human_decision_snapshots FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.human_decision_snapshots USING (org_id = NULLIF(current_setting('app.org_id', true), '')) WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));
ALTER TABLE rm.escalation_merges ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.escalation_merges FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.escalation_merges USING (org_id = NULLIF(current_setting('app.org_id', true), '')) WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));
ALTER TABLE rm.audit_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.audit_findings FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.audit_findings USING (org_id = NULLIF(current_setting('app.org_id', true), '')) WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

GRANT SELECT, INSERT ON rm.operator_decisions, rm.overrides, rm.review_resolutions, rm.signoffs,
  rm.human_decision_snapshots, rm.escalation_merges, rm.audit_findings TO rm_app;
