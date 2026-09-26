-- 0005 · Operations tables for jobs, workers, and request budgeting (§7.7, §10.2, §10.4a).
SET LOCAL ROLE rm_owner;

CREATE TABLE rm.worker_heartbeats (
  worker_id     text PRIMARY KEY,
  host          text NOT NULL,
  pid           integer NOT NULL,
  version       text NOT NULL,
  concurrency   integer NOT NULL,
  started_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rm.model_request_ledger (
  model_id      text NOT NULL,
  quota_day     date NOT NULL,
  requests_used integer NOT NULL DEFAULT 0,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (model_id, quota_day)
);

GRANT SELECT, INSERT, UPDATE ON rm.worker_heartbeats, rm.model_request_ledger TO rm_app;
