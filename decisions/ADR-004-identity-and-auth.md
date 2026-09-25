# ADR-004 Identity and authentication
Status: accepted
Owner: upeshchowdary
Date: 2026-09-25
Revisit by: 2026-12-01, or if the JWT signing algorithm changes on hosted Supabase
Reversibility: reversible — auth can be replaced without changing the data model

## Decision (one paragraph: what)

Two credential types are accepted: **Supabase Auth JWTs** (for human operators, reviewers and admins who
log in through the phone app or the review screen) and **scoped API keys** (for machine clients such as
Recovery Manager's agent). JWTs are verified server-side with `PyJWT` against the project's public JWKS
(`SUPABASE_JWKS_URL`); the app never calls Supabase Auth directly on the request path. The JWT `aud`
claim is validated against `SUPABASE_JWT_AUDIENCE` (default `authenticated`). API keys have the format
`rmk_<env>_<40 random base62 characters>`; the first 8 random characters are the public prefix (for
log-safe identification); the 32-byte SHA-256 digest is stored in `rm.api_keys.key_hash`. Key lookup goes
through the `rm.resolve_api_key()` SECURITY DEFINER function because the org is not known before the key
is found. Scopes are validated against the allowlist in `rm.api_keys.scopes`; an unknown scope is rejected
at creation time. All credentials resolve to a `Principal(kind, org_id, actor_id, role/scopes)` before
any route handler runs; the single `require(principal, permission)` call is the auth gate.

## Why

- **JWT verification with JWKS, not the service-role key**: Supabase publishes a JWKS endpoint. Verifying
  against it avoids sending the service-role key on every request. The `RS256` algorithm (asymmetric) is
  expected; the symmetric `HS256` path (using `SUPABASE_JWT_SECRET`) is supported as a fallback only.
- **API keys for machines**: A Supabase JWT has no concept of per-tenant scopes for a machine client.
  API keys carry explicit scopes and are namespaced to one org, matching the "narrowest key that works"
  deck principle.
- **SHA-256 storage, never plaintext**: The key is shown once at creation and never stored. Lookup is by
  hash. A breach of the `api_keys` table does not expose the key (though SHA-256 of a random 40-character
  base62 string has negligible collision risk, the 40 random chars make brute-force infeasible regardless).
- **Scope enforcement at the `require()` gate**: One place checks permissions; no route bypasses it. The
  authorization matrix in `roles.py` is static and fully unit-tested (test T-AUTH-01 in
  `test_authorization_matrix.py`).
- **404 not 403 for cross-org resources**: A caller authenticated to org A who requests a resource of
  org B must get 404, not 403, because the existence of the resource is itself org-private information.

## Rejected alternatives (and why)

- **Supabase RLS with `auth.uid()` for machine clients**: Machine clients do not have user JWTs. Custom
  API keys with explicit scopes are more auditable and revocable without revoking a user account.
- **OAuth2 client credentials**: Heavier to implement; no Supabase integration; out of scope for this build.
- **API key lookup as plain `rm_app_login` with a tenant context**: The org is unknown until the key is
  found, so a cross-tenant SECURITY DEFINER function is required. Doing it as `rm_app_login` with `org_id
  = NULL` (no context) would expose keys across orgs to anyone who can call the endpoint.
- **Using `service_role` key for JWT verification**: The service-role key bypasses RLS. Its use is
  strictly confined to storage operations (see `storage/service_client.py` and ADR-003). Using it for
  auth verification would violate the isolation model.

## Consequences

- `SUPABASE_JWKS_URL` must be set and reachable at boot for JWT auth to work. If absent, JWT auth is
  disabled and only API-key auth operates (the `/ready` endpoint reports `jwt: null`).
- The JWKS signing algorithm is listed in `§0.7` verify-first items. Verified at P1 database startup:
  see build-log.md for the finding (expected RS256; if HS256 is found, `SUPABASE_JWT_SECRET` is also set).
- API-key scopes are frozen at creation. Changing a key's scopes requires revocation and re-creation.
- The `rm_app_login` password is set by `returns-manager db migrate` from `DATABASE_URL`; it is never
  stored in a migration file.
