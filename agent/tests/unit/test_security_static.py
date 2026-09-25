"""Static security checks over the source tree and migrations (no database).

- T-SEC-08: SUPABASE_SERVICE_ROLE_KEY is read only in storage/ (config.py only declares it).
- Tenant helper: raw pool/connection usage appears only inside db/ (§6.3).
- Migrations: every table with org_id has RLS enabled AND forced with the NULLIF policy; exactly the four
  allowlisted SECURITY DEFINER functions exist, each pinned search_path, revoked from PUBLIC, granted to
  rm_app; no role is ever given BYPASSRLS/SUPERUSER.
"""

from __future__ import annotations

import re
from pathlib import Path

from returns_manager.config import AGENT_ROOT

SRC = AGENT_ROOT / "src" / "returns_manager"
MIGRATIONS = AGENT_ROOT / "migrations"
ALLOWLIST = {"claim_next_job", "resolve_api_key", "user_memberships", "reap_expired_leases"}


def _py_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _migrations_sql() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS.glob("*.sql")))


def test_t_sec_08_service_role_key_only_in_storage() -> None:
    """SUPABASE_SERVICE_ROLE_KEY must appear only in storage/ (exactly one module reads it)
    and in config.py (where it is declared). Nowhere else — not even as a presence check."""
    offenders = []
    for path in _py_files():
        rel = path.relative_to(SRC).as_posix()
        text = path.read_text(encoding="utf-8")
        if re.search(r"supabase_service_role_key|SUPABASE_SERVICE_ROLE_KEY", text) and not (
            rel.startswith("storage/") or rel == "config.py"
        ):
            offenders.append(rel)
    assert offenders == [], f"service-role key referenced outside storage/ and config.py: {offenders}"
    # And inside storage/ it is read (get_secret_value called) in exactly one module.
    readers = [
        p.name
        for p in (SRC / "storage").glob("*.py")
        if "get_secret_value" in p.read_text(encoding="utf-8")
        and "service_role" in p.read_text(encoding="utf-8")
    ]
    assert readers == ["service_client.py"]


def test_raw_pool_usage_only_inside_db_package() -> None:
    pattern = re.compile(r"\.connection\(|AsyncConnection\.connect|psycopg\.connect|AsyncConnectionPool\(")
    offenders = [
        p.relative_to(SRC).as_posix()
        for p in _py_files()
        if not p.relative_to(SRC).as_posix().startswith("db/")
        and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_every_tenant_table_has_forced_rls_and_the_nullif_policy() -> None:
    sql = _migrations_sql()
    tables = re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?rm\.(\w+) \((.*?)\n\);", sql, re.S)
    tenant_tables = [name for name, body in tables if re.search(r"^\s*org_id\s+text NOT NULL", body, re.M)]
    assert len(tenant_tables) >= 6, (
        f"expected >= 6 tenant tables, found {len(tenant_tables)}: {tenant_tables}"
    )
    for t in tenant_tables:
        assert f"ALTER TABLE rm.{t} ENABLE ROW LEVEL SECURITY;" in sql, t
        assert f"ALTER TABLE rm.{t} FORCE ROW LEVEL SECURITY;" in sql, t
        policy = re.search(rf"CREATE POLICY tenant_isolation ON rm\.{t}\n(.*?);", sql, re.S)
        assert policy, t
        assert policy.group(1).count("NULLIF(current_setting('app.org_id', true), '')") == 2, t


def test_security_definer_allowlist_is_exactly_four() -> None:
    sql = _migrations_sql()
    definers = re.findall(r"CREATE FUNCTION rm\.(\w+)\((.*?)AS \$\$", sql, re.S)
    names = {name for name, head in definers if "SECURITY DEFINER" in head}
    assert names == ALLOWLIST
    for name, head in definers:
        if name in ALLOWLIST:
            assert "SET search_path = pg_catalog, rm" in head, name
            assert re.search(rf"ALTER FUNCTION rm\.{name}\(.*?\) OWNER TO rm_definer;", sql), name
            assert re.search(rf"REVOKE ALL ON FUNCTION rm\.{name}\(.*?\) FROM PUBLIC;", sql), name
            assert re.search(rf"GRANT EXECUTE ON FUNCTION rm\.{name}\(.*?\) TO rm_app;", sql), name


def test_no_role_ever_gets_bypass_or_superuser() -> None:
    sql = _migrations_sql()
    assert re.search(r"(?<!NO)BYPASSRLS", sql) is None
    assert re.search(r"(?<!NO)SUPERUSER", sql) is None
    assert "GRANT rm_owner TO rm_app" not in sql
    assert "GRANT rm_definer TO rm_app" not in sql


def test_no_delete_grants_in_migrations() -> None:
    assert re.search(r"GRANT[^;]*DELETE", _migrations_sql()) is None
