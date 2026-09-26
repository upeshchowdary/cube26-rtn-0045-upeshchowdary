-- 0001 · Roles and schema (build prompt §6.2). Runs as the migrator (admin) role; later files SET ROLE rm_owner.
--
-- rm_owner      NOLOGIN  owns schema rm and every object in it; used only by `returns-manager db migrate`
-- rm_app        NOLOGIN  group role holding table privileges
-- rm_app_login  LOGIN    the API / worker / MCP / CLI connect as this role; NOSUPERUSER NOBYPASSRLS
-- rm_definer    NOLOGIN  owns the four audited SECURITY DEFINER functions (§6.4)
--
-- All roles carry NOBYPASSRLS explicitly. Cross-tenant access by the allowlisted functions is granted through
-- explicit, per-table policies `TO rm_definer` (see 0002, 0003), never through a bypass attribute.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rm_owner') THEN
    CREATE ROLE rm_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rm_app') THEN
    CREATE ROLE rm_app NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rm_app_login') THEN
    CREATE ROLE rm_app_login LOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rm_definer') THEN
    CREATE ROLE rm_definer NOLOGIN;
  END IF;
END
$$;

-- Enforce the attributes even if the roles pre-existed.
ALTER ROLE rm_owner     NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
ALTER ROLE rm_app       NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
ALTER ROLE rm_definer   NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
ALTER ROLE rm_app_login LOGIN   NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE INHERIT;
-- Tenant context must never persist at role level (it is set per transaction only).
ALTER ROLE rm_app_login RESET ALL;

GRANT rm_app TO rm_app_login;
-- The migrator may act as rm_owner (to create objects owned by it).
GRANT rm_owner TO CURRENT_USER;
-- rm_owner may hand function ownership to rm_definer, but does not inherit its privileges or policies.
GRANT rm_definer TO rm_owner WITH INHERIT FALSE, SET TRUE;

CREATE SCHEMA IF NOT EXISTS rm AUTHORIZATION rm_owner;
REVOKE ALL ON SCHEMA rm FROM PUBLIC;
DO $$
BEGIN
  -- Supabase API roles never touch schema rm (it is not exposed through the Data API either).
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON SCHEMA rm FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON SCHEMA rm FROM authenticated';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'REVOKE ALL ON SCHEMA rm FROM service_role';
  END IF;
END
$$;
GRANT USAGE ON SCHEMA rm TO rm_app;
-- CREATE is required for rm_definer to become the owner of functions in rm (ALTER FUNCTION ... OWNER TO).
-- rm_definer is NOLOGIN and only rm_owner can SET ROLE to it, so this grants nothing to the app.
GRANT USAGE, CREATE ON SCHEMA rm TO rm_definer;

-- Functions are executable by PUBLIC by default in PostgreSQL; never in schema rm.
ALTER DEFAULT PRIVILEGES FOR ROLE rm_owner IN SCHEMA rm REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE rm_definer IN SCHEMA rm REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

SET LOCAL ROLE rm_owner;

-- Applied migrations (§7.7). The runner refuses to run if an applied file's checksum changed.
CREATE TABLE IF NOT EXISTS rm.schema_migrations (
  version     text PRIMARY KEY,
  checksum    text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
  applied_at  timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT ON rm.schema_migrations TO rm_app;
