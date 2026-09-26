-- 0003 · Intake (§7.3) and the job queue (§7.4), plus cross-tenant functions 1 and 4 of the allowlist (§6.4).
SET LOCAL ROLE rm_owner;

CREATE TABLE rm.returns (
  return_id               text PRIMARY KEY,
  org_id                  text NOT NULL CHECK (org_id <> '') REFERENCES rm.organizations (org_id),
  client_id               text NOT NULL CHECK (client_id <> ''),       -- defaults to org_id (trigger below)
  record_id               text NOT NULL CHECK (record_id ~ '^RTN-[0-9]{4}(-[0-9]+)?$'),
  unit_id                 text NOT NULL CHECK (unit_id <> ''),
  order_id                text NOT NULL CHECK (order_id <> ''),
  ordered_sku             text,
  ordered_asin            text,
  return_seq              integer NOT NULL CHECK (return_seq >= 1),
  status                  text NOT NULL DEFAULT 'capturing' CHECK (status IN (
                            'capturing', 'queued', 'inspecting', 'pending', 'awaiting_operator',
                            'awaiting_review', 'awaiting_signoff', 'finalized', 'needs_attention')),
  created_by              text NOT NULL,
  created_at              timestamptz NOT NULL DEFAULT now(),
  submitted_at            timestamptz,
  finalized_at            timestamptz,
  current_record_version  integer,
  UNIQUE (org_id, return_id),          -- target of composite FKs: a child row can never cross orgs
  UNIQUE (org_id, record_id),
  UNIQUE (org_id, unit_id, return_seq)
);

CREATE FUNCTION rm.returns_default_client_id() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, rm AS $$
BEGIN
  IF NEW.client_id IS NULL THEN
    NEW.client_id := NEW.org_id;
  END IF;
  RETURN NEW;
END
$$;
REVOKE ALL ON FUNCTION rm.returns_default_client_id() FROM PUBLIC;
CREATE TRIGGER returns_default_client_id BEFORE INSERT ON rm.returns
  FOR EACH ROW EXECUTE FUNCTION rm.returns_default_client_id();

CREATE TABLE rm.return_photos (
  photo_id              text PRIMARY KEY,
  org_id                text NOT NULL CHECK (org_id <> ''),
  return_id             text NOT NULL,
  slot                  integer NOT NULL CHECK (slot BETWEEN 1 AND 3),
  alias                 text CHECK (alias IN ('P1', 'P2', 'P3')),
  role_hint             text,
  storage_key_original  text NOT NULL UNIQUE,
  storage_key_analysis  text UNIQUE,
  mime                  text NOT NULL CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp',
                                                      'image/heic', 'image/heif')),
  bytes                 bigint NOT NULL CHECK (bytes > 0),
  width                 integer CHECK (width > 0),
  height                integer CHECK (height > 0),
  sha256_original       text NOT NULL CHECK (sha256_original ~ '^[0-9a-f]{64}$'),
  sha256_analysis       text CHECK (sha256_analysis ~ '^[0-9a-f]{64}$'),
  phash                 bit(64),
  transform_version     text,
  client_transform      jsonb,
  exif_summary          jsonb,
  quality               jsonb,
  quality_status        text CHECK (quality_status IN ('pass', 'warn', 'fail')),
  captured_at_client    timestamptz,
  uploaded_at           timestamptz NOT NULL DEFAULT now(),
  uploaded_by           text NOT NULL,
  idempotency_key       text,
  retake_of             text REFERENCES rm.return_photos (photo_id),
  superseded            boolean NOT NULL DEFAULT false,
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id),
  UNIQUE (org_id, return_id, sha256_original),
  -- Storage keys are org/{org_id}/returns/{return_id}/{uuid4}.{ext} (§6.5): enforced here too.
  CHECK (starts_with(storage_key_original, 'org/' || org_id || '/returns/' || return_id || '/')),
  CHECK (storage_key_analysis IS NULL
         OR starts_with(storage_key_analysis, 'org/' || org_id || '/returns/' || return_id || '/'))
);

CREATE TABLE rm.operator_observations (
  obs_id          text PRIMARY KEY,
  org_id          text NOT NULL CHECK (org_id <> ''),
  return_id       text NOT NULL,
  observed_state  text NOT NULL CHECK (observed_state IN ('factory_sealed', 'opened_unused', 'signs_of_use',
                                                          'damaged', 'empty_box', 'uncertain')),
  operator_id     text NOT NULL,
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  note            text,
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id)
);

CREATE TABLE rm.inspection_jobs (
  job_id             text PRIMARY KEY,
  org_id             text NOT NULL CHECK (org_id <> ''),
  return_id          text NOT NULL,
  kind               text NOT NULL CHECK (kind IN ('judgment', 'escalation', 'audit', 'reinspection')),
  status             text NOT NULL DEFAULT 'pending' CHECK (status IN (
                       'pending', 'in_progress', 'succeeded', 'failed_retryable', 'needs_attention', 'cancelled')),
  priority           integer NOT NULL DEFAULT 0,
  idempotency_key    text NOT NULL CHECK (idempotency_key <> ''),
  attempts           integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  max_attempts       integer NOT NULL DEFAULT 5 CHECK (max_attempts >= 1),
  next_attempt_at    timestamptz NOT NULL DEFAULT now(),
  lease_owner        text,
  lease_expires_at   timestamptz,
  last_error_class   text,
  last_error_detail  text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (org_id, return_id) REFERENCES rm.returns (org_id, return_id),
  UNIQUE (org_id, idempotency_key)
);
CREATE INDEX inspection_jobs_claimable
  ON rm.inspection_jobs (status, next_attempt_at, priority DESC, created_at)
  WHERE status IN ('pending', 'failed_retryable');
CREATE INDEX inspection_jobs_in_progress
  ON rm.inspection_jobs (org_id, lease_expires_at)
  WHERE status = 'in_progress';

-- ── Row-level security ─────────────────────────────────────────────────────
ALTER TABLE rm.returns ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.returns FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.returns
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.return_photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.return_photos FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.return_photos
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.operator_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.operator_observations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.operator_observations
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.inspection_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.inspection_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.inspection_jobs
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));
-- Cross-tenant claim/reap for rm.claim_next_job() and rm.reap_expired_leases() only.
CREATE POLICY definer_select ON rm.inspection_jobs FOR SELECT TO rm_definer USING (true);
CREATE POLICY definer_update ON rm.inspection_jobs FOR UPDATE TO rm_definer USING (true) WITH CHECK (true);

-- ── Privileges (no DELETE anywhere) ────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE ON rm.returns, rm.return_photos, rm.operator_observations, rm.inspection_jobs
  TO rm_app;
GRANT SELECT, UPDATE ON rm.inspection_jobs TO rm_definer;

-- ── Cross-tenant functions (allowlist §6.4, items 1 and 4) ─────────────────
-- Claims one job across orgs: due pending/retryable jobs, or in-progress jobs whose lease expired
-- (dead worker), skipping orgs already at their in-flight cap; highest priority, then oldest first.
-- Returns 0 or 1 row; the worker then sets tenant context to the returned org_id for all further work.
CREATE FUNCTION rm.claim_next_job(worker_id text, lease_s integer, max_inflight_per_org integer)
RETURNS SETOF rm.inspection_jobs
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, rm
AS $$
  WITH candidate AS (
    SELECT j.job_id
    FROM rm.inspection_jobs AS j
    WHERE (
            (j.status IN ('pending', 'failed_retryable') AND j.next_attempt_at <= now())
         OR (j.status = 'in_progress' AND j.lease_expires_at < now())
          )
      AND (
            SELECT count(*)
            FROM rm.inspection_jobs AS x
            WHERE x.org_id = j.org_id
              AND x.status = 'in_progress'
              AND x.lease_expires_at >= now()
          ) < claim_next_job.max_inflight_per_org
    ORDER BY j.priority DESC, j.created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
  )
  UPDATE rm.inspection_jobs AS t
  SET status = 'in_progress',
      attempts = t.attempts + 1,
      lease_owner = claim_next_job.worker_id,
      lease_expires_at = now() + make_interval(secs => claim_next_job.lease_s),
      updated_at = now()
  FROM candidate
  WHERE t.job_id = candidate.job_id
  RETURNING t.*
$$;

-- Returns expired in-progress jobs to failed_retryable (a dead worker's lease).
CREATE FUNCTION rm.reap_expired_leases(max_rows integer)
RETURNS integer
LANGUAGE sql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, rm
AS $$
  WITH expired AS (
    SELECT j.job_id
    FROM rm.inspection_jobs AS j
    WHERE j.status = 'in_progress' AND j.lease_expires_at < now()
    ORDER BY j.lease_expires_at
    FOR UPDATE SKIP LOCKED
    LIMIT reap_expired_leases.max_rows
  ), updated AS (
    UPDATE rm.inspection_jobs AS t
    SET status = 'failed_retryable',
        lease_owner = NULL,
        lease_expires_at = NULL,
        last_error_class = 'lease_expired',
        next_attempt_at = now(),
        updated_at = now()
    FROM expired
    WHERE t.job_id = expired.job_id
    RETURNING 1
  )
  SELECT count(*)::integer FROM updated
$$;

ALTER FUNCTION rm.claim_next_job(text, integer, integer) OWNER TO rm_definer;
ALTER FUNCTION rm.reap_expired_leases(integer) OWNER TO rm_definer;
REVOKE ALL ON FUNCTION rm.claim_next_job(text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION rm.reap_expired_leases(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rm.claim_next_job(text, integer, integer) TO rm_app;
GRANT EXECUTE ON FUNCTION rm.reap_expired_leases(integer) TO rm_app;
