-- 0007 · Inspection runs, model tool calls and inspection results (§7.4). Tenant tables: RLS enabled and forced.
SET LOCAL ROLE rm_owner;

-- One row per model session (judgment / escalation / audit), or per skipped inspection (§11.2a).
CREATE TABLE rm.inspection_runs (
  inspection_id            text PRIMARY KEY,
  org_id                   text NOT NULL CHECK (org_id <> ''),
  return_id                text NOT NULL,
  job_id                   text,
  kind                     text NOT NULL CHECK (kind IN ('judgment', 'escalation', 'audit', 'reinspection')),
  model_id                 text,
  effort                   text,
  output_mode              text CHECK (output_mode IN ('json_schema', 'json_prompted')),
  prompt_id                text,
  prompt_version           text,
  prompt_sha256            text,
  judgment_schema_version  text,
  context_manifest         jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at               timestamptz NOT NULL DEFAULT now(),
  completed_at             timestamptz,
  status                   text NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
  skip_reasons             text[],
  api_requests             integer NOT NULL DEFAULT 0 CHECK (api_requests >= 0),
  tool_calls               integer NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
  usage                    jsonb NOT NULL DEFAULT '{}'::jsonb,
  cost_usd_micros          bigint,                 -- PAID-EQUIVALENT (free tier used)
  latency_ms               integer,
  provider_interaction_ids text[] NOT NULL DEFAULT '{}',
  finish_reasons           text[] NOT NULL DEFAULT '{}',
  safety_block             jsonb,
  error_class              text,
  error_detail             text,
  output                   jsonb,                  -- validated structured output only; never thinking content
  output_sha256            text CHECK (output_sha256 IS NULL OR output_sha256 ~ '^[0-9a-f]{64}$'),
  validation_report        jsonb,
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id),
  UNIQUE (org_id, inspection_id)
);
CREATE INDEX inspection_runs_return ON rm.inspection_runs (org_id, return_id, started_at);

CREATE TABLE rm.model_tool_calls (
  tool_call_id    text PRIMARY KEY,
  org_id          text NOT NULL CHECK (org_id <> ''),
  inspection_id   text NOT NULL,
  seq             integer NOT NULL CHECK (seq >= 1),
  round_trip      integer NOT NULL CHECK (round_trip >= 1),
  tool_name       text NOT NULL,
  input           jsonb NOT NULL,
  output_summary  jsonb NOT NULL,
  status          text NOT NULL CHECK (status IN ('ok', 'error', 'budget_exhausted')),
  latency_ms      integer,
  FOREIGN KEY (org_id, inspection_id) REFERENCES rm.inspection_runs (org_id, inspection_id),
  UNIQUE (org_id, inspection_id, seq)
);

CREATE TABLE rm.inspection_results (
  result_id                 text PRIMARY KEY,
  org_id                    text NOT NULL CHECK (org_id <> ''),
  return_id                 text NOT NULL,
  inspection_id             text NOT NULL,
  identity_match            text NOT NULL CHECK (identity_match IN ('yes', 'no', 'uncertain')),
  fused_identity            jsonb NOT NULL,
  unit_presence             text NOT NULL,
  completeness_status       text NOT NULL CHECK (completeness_status IN ('complete', 'incomplete', 'uncertain')),
  components                jsonb NOT NULL,
  cosmetic_grade            text,
  amazon_condition          text NOT NULL,
  listing_blockers          text[] NOT NULL DEFAULT '{}',
  condition                 jsonb NOT NULL,
  model_observed_state      text,
  claim_signals             jsonb NOT NULL,
  uncertainties             jsonb NOT NULL,
  retake_requests           jsonb NOT NULL,
  validator_actions         jsonb NOT NULL,
  checks                    jsonb NOT NULL,
  escalation_state          text NOT NULL CHECK (escalation_state IN ('not_triggered', 'triggered_not_run')),
  recommended_disposition   text CHECK (recommended_disposition IN ('restock', 'refurbish', 'liquidate', 'dispose')),
  no_recommendation_reason  text,
  provisional               boolean NOT NULL,
  relistable_as_is          boolean,
  disposition               jsonb NOT NULL,         -- the full decision
  disposition_inputs        jsonb NOT NULL,         -- canonical inputs (what-if simulation, §12.6)
  requires_review           boolean NOT NULL,
  review_reasons            text[] NOT NULL DEFAULT '{}',
  requires_signoff          boolean NOT NULL,
  created_at                timestamptz NOT NULL DEFAULT now(),
  CHECK (recommended_disposition IS NOT NULL OR (no_recommendation_reason IS NOT NULL AND requires_review)),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id),
  FOREIGN KEY (org_id, inspection_id) REFERENCES rm.inspection_runs (org_id, inspection_id)
);
CREATE INDEX inspection_results_return ON rm.inspection_results (org_id, return_id, created_at);

-- ── Row-level security ─────────────────────────────────────────────────────
ALTER TABLE rm.inspection_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.inspection_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.inspection_runs
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.model_tool_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.model_tool_calls FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.model_tool_calls
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.inspection_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.inspection_results FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.inspection_results
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

-- ── Privileges (no DELETE anywhere; all three are append-only by grant: a run is inserted in its final state) ─
GRANT SELECT, INSERT ON rm.inspection_runs, rm.model_tool_calls, rm.inspection_results TO rm_app;
