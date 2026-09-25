# ADR-003 Tenancy mechanism
Status: accepted
Owner: upeshchowdary
Date: 2026-09-25
Revisit by: 2026-11-01, or if a new cross-tenant operation is needed (adding one requires a new ADR and human approval)
Reversibility: irreversible — changing the tenancy model requires a breaking schema migration

## Decision (one paragraph: what)

Every tenant table in schema `rm` carries `org_id text NOT NULL CHECK (org_id <> '')` and has row-level
security **enabled and forced** (so even the table owner is subject to it). The single policy on each table
is `org_id = NULLIF(current_setting('app.org_id', true), '')`. Tenant context is set **per transaction**
via `set_config('app.org_id', <org>, true)` (the `true` makes it transaction-local, so it cannot leak to
the next user of a pooled connection). All application code opens DB transactions only through
`db.tenant.transaction(org_id)`. The application connects as `rm_app_login` (NOSUPERUSER, NOBYPASSRLS)
and refuses to boot if its role can bypass RLS. Cross-tenant operations are restricted to exactly four
audited `SECURITY DEFINER` functions owned by `rm_definer` (NOLOGIN, NOBYPASSRLS): `claim_next_job`,
`resolve_api_key`, `user_memberships`, and `reap_expired_leases`. Each of these functions is pinned with
`SET search_path = pg_catalog, rm`, revoked from PUBLIC, and granted only to `rm_app`.

## Why

- **Enforcement at the database layer**: RLS enforced on every tenant table means no application bug or
  missing middleware check can ever leak one org's data to another. A green isolation test under a bypass
  role would prove nothing; that is why `rm_app_login` is NOBYPASSRLS and why the boot check refuses to
  run under a bypass role.
- **Transaction-local context (`true` flag)**: The `set_config` `is_local = true` argument makes the
  setting die with the transaction, preventing context from bleeding to the next connection pool user.
- **Fail-closed on missing context**: `NULLIF(current_setting('app.org_id', true), '')` converts both
  `NULL` and the empty string `''` to `NULL`, so a missing tenant context matches zero rows and rejects
  all writes — it never fails open.
- **No bypass role for the app**: Engineering Rule 1 requires proving a second org sees zero rows. That
  proof is only meaningful if the app connects with a role that cannot bypass the policy it is testing.
- **SECURITY DEFINER with NOBYPASSRLS**: Postgres SECURITY DEFINER runs as the function owner
  (`rm_definer`), which is NOLOGIN and NOBYPASSRLS. Cross-tenant visibility is achieved through explicit
  per-table `TO rm_definer` policies, not a bypass attribute — so the scope of each function's cross-org
  access is auditable from the SQL alone.

## Rejected alternatives (and why)

- **Application-side multi-tenancy (WHERE org_id = ?)**: Any query that forgets the clause leaks data.
  RLS is a defence-in-depth layer that the database enforces regardless of application code.
- **Separate schemas or databases per tenant**: Too complex for this build; overkill for two demo orgs.
- **Using Supabase's built-in `auth.uid()` in RLS**: Supabase Auth UIDs are user-level, not org-level.
  A user belongs to multiple orgs; the policy must track which org the current **operation** is for,
  not which user is logged in.
- **Using a transaction SET LOCAL on `role`**: Roles cannot be set per-transaction in Postgres without
  a SECURITY DEFINER trampoline; the GUC approach is simpler, auditable and does not require superuser.

## Consequences

- A test `test_every_tenant_table_has_forced_rls_and_the_nullif_policy` checks every CREATE TABLE
  that contains `org_id text NOT NULL` and asserts both `ENABLE/FORCE ROW LEVEL SECURITY` and the
  exact NULLIF policy wording. Any future migration adding a tenant table must follow the pattern.
- The four allowlisted cross-tenant functions are the only permitted exceptions. Adding a fifth requires
  a new ADR approved by the human, a `TO rm_definer` policy on the affected tables, and an update to
  `tests/unit/test_security_static.py::test_security_definer_allowlist_is_exactly_four`.
- `db.tenant.transaction(None)` opens a transaction without context. It is the **only** way to call
  cross-tenant functions and to write global `system_controls` rows from the CLI. Application routes and
  the worker must always pass an org_id.
