-- 0002 · Tenancy and security tables (§6, §7.1) and two of the four cross-tenant functions (§6.4).
SET LOCAL ROLE rm_owner;

-- Every tenant table: org_id text NOT NULL CHECK (org_id <> ''), RLS enabled AND forced, one policy
--   tenant_isolation: org_id = NULLIF(current_setting('app.org_id', true), '')
-- NULLIF makes a missing/empty tenant context match nothing (fail-closed).

CREATE TABLE rm.organizations (
  org_id      text PRIMARY KEY CHECK (org_id <> ''),
  name        text NOT NULL CHECK (name <> ''),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rm.memberships (
  user_id         uuid NOT NULL,
  org_id          text NOT NULL CHECK (org_id <> '') REFERENCES rm.organizations (org_id),
  role            text NOT NULL CHECK (role IN ('operator', 'reviewer', 'admin')),
  operator_label  text NOT NULL CHECK (operator_label <> ''),
  created_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, org_id),
  UNIQUE (org_id, operator_label)
);

CREATE TABLE rm.api_keys (
  key_id        text PRIMARY KEY,
  org_id        text NOT NULL CHECK (org_id <> '') REFERENCES rm.organizations (org_id),
  name          text NOT NULL CHECK (name <> ''),
  key_prefix    text NOT NULL CHECK (char_length(key_prefix) = 8),
  key_hash      bytea NOT NULL UNIQUE CHECK (octet_length(key_hash) = 32),
  scopes        text[] NOT NULL CHECK (
                  cardinality(scopes) > 0
                  AND scopes <@ ARRAY['returns:write', 'returns:read', 'review:write',
                                      'evidence:read', 'metrics:read', 'admin']::text[]),
  created_by    text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  expires_at    timestamptz,
  revoked_at    timestamptz,
  last_used_at  timestamptz
);

-- Kill switch (§6.7). scope = 'global' or an org_id. Effective value = global AND org (both default on).
CREATE TABLE rm.system_controls (
  scope       text NOT NULL CHECK (scope <> ''),
  control     text NOT NULL CHECK (control IN ('auto_disposition_enabled', 'model_calls_enabled',
                                              'audit_enabled', 'escalation_enabled')),
  enabled     boolean NOT NULL,
  reason      text NOT NULL CHECK (btrim(reason) <> ''),
  updated_by  text NOT NULL CHECK (updated_by <> ''),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (scope, control)
);

-- ── Row-level security ─────────────────────────────────────────────────────
ALTER TABLE rm.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.organizations
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));

ALTER TABLE rm.memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.memberships
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));
-- Cross-tenant read for rm.user_memberships() only (the function's owner is rm_definer).
CREATE POLICY definer_read ON rm.memberships FOR SELECT TO rm_definer USING (true);

ALTER TABLE rm.api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.api_keys FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON rm.api_keys
  USING      (org_id = NULLIF(current_setting('app.org_id', true), ''))
  WITH CHECK (org_id = NULLIF(current_setting('app.org_id', true), ''));
-- Cross-tenant read for rm.resolve_api_key() only.
CREATE POLICY definer_read ON rm.api_keys FOR SELECT TO rm_definer USING (true);

-- system_controls has no org_id: its scope is either an org or 'global'.
--   read:  global rows + the current org's rows
--   write: the current org's rows; global rows only from a transaction WITHOUT tenant context
--          (the CLI), so no request handled under an org's context can ever change a global control.
ALTER TABLE rm.system_controls ENABLE ROW LEVEL SECURITY;
ALTER TABLE rm.system_controls FORCE ROW LEVEL SECURITY;
CREATE POLICY controls_read ON rm.system_controls FOR SELECT
  USING (scope = 'global' OR scope = NULLIF(current_setting('app.org_id', true), ''));
CREATE POLICY controls_insert ON rm.system_controls FOR INSERT
  WITH CHECK (
    scope = NULLIF(current_setting('app.org_id', true), '')
    OR (scope = 'global' AND NULLIF(current_setting('app.org_id', true), '') IS NULL));
CREATE POLICY controls_update ON rm.system_controls FOR UPDATE
  USING (
    scope = NULLIF(current_setting('app.org_id', true), '')
    OR (scope = 'global' AND NULLIF(current_setting('app.org_id', true), '') IS NULL))
  WITH CHECK (
    scope = NULLIF(current_setting('app.org_id', true), '')
    OR (scope = 'global' AND NULLIF(current_setting('app.org_id', true), '') IS NULL));

-- ── Privileges (no DELETE anywhere) ────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE ON rm.organizations, rm.memberships, rm.api_keys, rm.system_controls TO rm_app;
GRANT SELECT ON rm.memberships, rm.api_keys TO rm_definer;

-- ── Cross-tenant functions (allowlist §6.4, items 2 and 3) ─────────────────
CREATE FUNCTION rm.resolve_api_key(key_hash bytea)
RETURNS TABLE (key_id text, org_id text, scopes text[], expires_at timestamptz, revoked_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, rm
AS $$
  SELECT k.key_id, k.org_id, k.scopes, k.expires_at, k.revoked_at
  FROM rm.api_keys AS k
  WHERE k.key_hash = resolve_api_key.key_hash
$$;

CREATE FUNCTION rm.user_memberships(user_id uuid)
RETURNS TABLE (org_id text, role text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, rm
AS $$
  SELECT m.org_id, m.role
  FROM rm.memberships AS m
  WHERE m.user_id = user_memberships.user_id
  ORDER BY m.org_id
$$;

ALTER FUNCTION rm.resolve_api_key(bytea) OWNER TO rm_definer;
ALTER FUNCTION rm.user_memberships(uuid) OWNER TO rm_definer;
REVOKE ALL ON FUNCTION rm.resolve_api_key(bytea) FROM PUBLIC;
REVOKE ALL ON FUNCTION rm.user_memberships(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rm.resolve_api_key(bytea) TO rm_app;
GRANT EXECUTE ON FUNCTION rm.user_memberships(uuid) TO rm_app;
