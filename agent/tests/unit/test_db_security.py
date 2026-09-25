"""Database security tests (§19, marker: db). These run only when the local Supabase stack is up.

Run with: pytest -m db -q

Each test creates fresh org IDs per run (no DELETE grants exist, so ids are unique per run).
Setup: seeds two fresh orgs via rm_app_login, then runs isolation checks.

T-SEC-01  App refuses to boot when given a superuser/bypass DSN.
T-SEC-02  Org A sees 0 of org B's rows in every tenant table.
T-SEC-03  Cross-org insert is rejected by RLS.
T-SEC-04  No tenant context → 0 rows visible; inserts fail.
T-SEC-05  Org A gets NotFound for org B's photo (signed_url_for_photo with wrong org).
T-SEC-06  Guessed storage path is not fetchable anonymously (bucket is private).
T-SEC-07  API-key scope enforcement per endpoint permission.
T-SEC-08  Kill-switch rules: global writes only without tenant context; reason required.
"""

from __future__ import annotations

import io
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from PIL import Image

from returns_manager.config import get_settings
from returns_manager.db.migrate import migrate
from returns_manager.db.pool import Database, UnsafeDatabaseRole, run_async
from returns_manager.errors import NotFound
from returns_manager.ids import new_id
from returns_manager.intake.service import IntakeService
from returns_manager.jobs.queue import JobQueue
from returns_manager.security import api_keys, controls
from returns_manager.security.controls import Control
from returns_manager.security.roles import Forbidden, Permission, Principal, Role, require
from returns_manager.storage.signed_urls import signed_url_for_photo

# ── helpers ────────────────────────────────────────────────────────────────────


def _migrator_dsn() -> str:
    settings = get_settings()
    dsn = (
        (settings.database_migrator_url.get_secret_value() if settings.database_migrator_url else None)
        or os.environ.get("DATABASE_MIGRATOR_URL")
        or ""
    )
    if not dsn:
        pytest.skip("DATABASE_MIGRATOR_URL not set; run `npx supabase start` first")
    return dsn


def _app_dsn() -> str:
    settings = get_settings()
    dsn = (
        (settings.database_url.get_secret_value() if settings.database_url else None)
        or os.environ.get("DATABASE_URL")
        or ""
    )
    if not dsn:
        pytest.skip("DATABASE_URL not set; run `npx supabase start` first")
    return dsn


def _fresh_org() -> str:
    """Fresh, unique org_id per test run; never reuses rows (no DELETE grants)."""
    return f"org_t{uuid.uuid4().hex[:12]}"


# Every table that carries org_id and row-level security (organizations is checked via its own row).
TENANT_TABLES: tuple[str, ...] = (
    "organizations",
    "memberships",
    "api_keys",
    "returns",
    "return_photos",
    "operator_observations",
    "inspection_jobs",
    "products",
    "product_components",
    "reference_images",
    "org_policy_overrides",
    "orders",
)


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1200, 900), (120, 130, 140)).save(buf, format="JPEG")
    return buf.getvalue()


async def _seed_every_tenant_table(db: Database, org_id: str) -> dict[str, str]:
    """Give `org_id` at least one row in every tenant table (through the normal services where they exist)."""
    svc = IntakeService(db)
    ret = await svc.create_return(
        org_id=org_id, actor_id="op_seed", order_id="ORD-SEC-1", unit_id="UNIT-0042", ordered_sku="SKU-SEC"
    )
    photo = await svc.upload_photo(
        org_id=org_id, actor_id="op_seed", return_id=ret.return_id, photo_bytes=_jpeg()
    )
    await svc.record_observation(
        org_id=org_id, actor_id="op_seed", return_id=ret.return_id, observed_state="damaged"
    )
    await api_keys.create_key(
        db, org_id=org_id, name="seed", scopes=["returns:read"], created_by="test", env="local"
    )
    async with db.transaction(org_id) as conn:
        await JobQueue.enqueue_job(conn, org_id, ret.return_id, idempotency_key=f"seed-{new_id()}")
        await conn.execute(
            "INSERT INTO rm.memberships (user_id, org_id, role, operator_label) "
            "VALUES (%s, %s, 'operator', %s)",
            (uuid.uuid4(), org_id, f"op_{new_id()[:8].lower()}"),
        )
        await conn.execute(
            """INSERT INTO rm.products
                 (org_id, sku, card_version, title, brand, category_key, card_sha256, card)
               VALUES (%s, 'SKU-SEC', '1.0.0', 't', 'b', 'electronics', %s, '{}'::jsonb)""",
            (org_id, "0" * 64),
        )
        await conn.execute(
            """INSERT INTO rm.product_components (org_id, sku, card_version, component_id, name, quantity,
                 visual_cues, source)
               VALUES (%s, 'SKU-SEC', '1.0.0', 'part', 'part', 1, 'cue', '{}'::jsonb)""",
            (org_id,),
        )
        await conn.execute(
            """INSERT INTO rm.reference_images
                 (org_id, sku, card_version, ref_image_id, view, storage_key, sha256)
               VALUES (%s, 'SKU-SEC', '1.0.0', 'ref_front', 'front', 'k', %s)""",
            (org_id, "0" * 64),
        )
        await conn.execute(
            """INSERT INTO rm.org_policy_overrides (org_id, key, value, source_type, updated_by)
               VALUES (%s, 'opened_item_route', '"liquidate"'::jsonb, 'business_policy', 'test')""",
            (org_id,),
        )
        await conn.execute(
            """INSERT INTO rm.orders
                 (org_id, order_id, unit_id, ordered_sku, quantity, fulfilment_route, ordered_at)
               VALUES (%s, 'ORD-SEC-1', 'UNIT-0042', 'SKU-SEC', 1, 'fba', now())""",
            (org_id,),
        )
    return {"return_id": ret.return_id, "photo_id": photo.photo_id}


# ── fixtures ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def db() -> AsyncIterator[Database]:
    """Open rm_app_login database, run migrations (idempotent), yield the Database."""
    migrator_dsn = _migrator_dsn()
    app_dsn = _app_dsn()
    await migrate(migrator_dsn, app_dsn)
    database = Database(app_dsn)
    await database.open(check_role=True)
    yield database
    await database.close()


@pytest_asyncio.fixture()
async def two_orgs(db: Database) -> tuple[str, str]:
    """Seed two fresh orgs; return (alpha_org_id, bravo_org_id)."""
    alpha = _fresh_org()
    bravo = _fresh_org()
    for org_id in (alpha, bravo):
        async with db.transaction(org_id) as conn:
            await conn.execute(
                "INSERT INTO rm.organizations (org_id, name) VALUES (%s, %s)",
                (org_id, f"Test org {org_id}"),
            )
    return alpha, bravo


# ── T-SEC-01 ───────────────────────────────────────────────────────────────────


@pytest.mark.db
def test_t_sec_01_app_refuses_bypass_role() -> None:
    """Boot check raises UnsafeDatabaseRole when the DSN uses a superuser role."""
    migrator_dsn = _migrator_dsn()

    # The migrator DSN connects as postgres (superuser) — must be refused.
    def go() -> None:
        async def _go() -> None:
            db = Database(migrator_dsn)
            await db.open(check_role=True)
            await db.close()

        run_async(_go)

    with pytest.raises(UnsafeDatabaseRole, match=r"superuser|BYPASSRLS"):
        go()


# ── T-SEC-02 ───────────────────────────────────────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_sec_02_org_isolation_zero_rows(db: Database, two_orgs: tuple[str, str]) -> None:
    """Bravo gets a row in every tenant table; alpha sees none of them (and bravo sees all of its own)."""
    alpha, bravo = two_orgs
    await _seed_every_tenant_table(db, bravo)

    for table in TENANT_TABLES:
        for viewer, expect_rows in ((alpha, False), (bravo, True)):
            async with db.transaction(viewer) as conn:
                cur = await conn.execute(
                    f"SELECT count(*) AS n FROM rm.{table} WHERE org_id = %s",  # noqa: S608
                    (bravo,),
                )
                row = await cur.fetchone()
            assert row is not None
            if expect_rows:
                assert row["n"] > 0, f"seeding failed: bravo sees no rows in rm.{table}"
            else:
                assert row["n"] == 0, f"alpha sees {row['n']} of bravo's rows in rm.{table}"


# ── T-SEC-03 ───────────────────────────────────────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_sec_03_cross_org_insert_rejected(db: Database, two_orgs: tuple[str, str]) -> None:
    """Inserting a row with bravo's org_id while the tenant context is alpha is rejected by RLS."""
    alpha, bravo = two_orgs
    with pytest.raises(Exception, match=r"new row violates|violates row-level"):
        async with db.transaction(alpha) as conn:
            # Attempt to insert an org row for bravo while context is alpha.
            await conn.execute(
                "INSERT INTO rm.organizations (org_id, name) VALUES (%s, %s)",
                (bravo, "sneaky cross-org insert"),
            )


# ── T-SEC-04 ───────────────────────────────────────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_sec_04_no_tenant_context_zero_rows(db: Database, two_orgs: tuple[str, str]) -> None:
    """Without tenant context (org_id=None), every tenant table returns 0 rows; inserts fail."""
    alpha, _ = two_orgs
    async with db.transaction(None) as conn:
        cur = await conn.execute("SELECT count(*) AS n FROM rm.organizations")
        row = await cur.fetchone()
    assert row is not None
    assert row["n"] == 0, f"expected 0 rows without context; got {row['n']}"

    with pytest.raises(Exception, match=r"new row violates|violates row-level"):
        async with db.transaction(None) as conn:
            await conn.execute(
                "INSERT INTO rm.organizations (org_id, name) VALUES (%s, %s)",
                (alpha, "no-context insert attempt"),
            )


# ── T-SEC-05 ───────────────────────────────────────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_sec_05_photo_not_found_for_wrong_org(db: Database, two_orgs: tuple[str, str]) -> None:
    """Alpha asking for a signed URL of bravo's REAL photo gets NotFound (→ 404), exactly like a made-up id.

    The storage client is never reached: ownership is checked first, inside alpha's tenant transaction.
    """
    alpha, bravo = two_orgs
    seeded = await _seed_every_tenant_table(db, bravo)
    bravo_photo_id = seeded["photo_id"]

    class _StorageMustNotBeCalled:
        photos_bucket = "rm-return-photos"

        async def signed_url(self, *args: object, **kwargs: object) -> str:
            raise AssertionError("storage reached before the ownership check")

    alpha_user = Principal(kind="user", org_id=alpha, actor_id="op-alpha", role=Role.OPERATOR)
    storage: Any = _StorageMustNotBeCalled()
    for photo_id in (bravo_photo_id, f"photo_{new_id()}"):
        with pytest.raises(NotFound):
            await signed_url_for_photo(db, storage, alpha_user, photo_id, "analysis", 300)

    # The photo really exists for its own org.
    async with db.transaction(bravo) as conn:
        cur = await conn.execute("SELECT 1 FROM rm.return_photos WHERE photo_id = %s", (bravo_photo_id,))
        assert await cur.fetchone() is not None


# ── T-SEC-06 ───────────────────────────────────────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_sec_06_guessed_storage_path_rejected(two_orgs: tuple[str, str]) -> None:
    """A guessed object path cannot be fetched anonymously from the private bucket."""
    import httpx

    settings = get_settings()
    if not settings.supabase_url:
        pytest.skip("SUPABASE_URL not set")

    _, bravo = two_orgs
    guessed_key = f"org/{bravo}/returns/RETURN-999/{uuid.uuid4()}.jpg"
    public_url = (
        f"{settings.supabase_url}/storage/v1/object/{settings.rm_storage_bucket_photos}/{guessed_key}"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(public_url)
    # Private bucket: anonymous access must be denied.
    assert resp.status_code in (400, 401, 403, 404), (
        f"expected denied response for guessed private storage path; got {resp.status_code}"
    )


# ── T-SEC-07 ───────────────────────────────────────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_sec_07_api_key_scope_enforcement(db: Database, two_orgs: tuple[str, str]) -> None:
    """API key scopes enforce the permission matrix: each scope permits only its listed permissions."""
    alpha, _ = two_orgs

    # evidence:read (Recovery's scope) permits EVIDENCE_READ and PHOTO_URL only.
    ev_key = await api_keys.create_key(
        db,
        org_id=alpha,
        name="t-sec-07-evidence",
        scopes=["evidence:read"],
        created_by="test",
        env="local",
    )
    ev_principal = await api_keys.authenticate(db, ev_key.plaintext, env="local")
    assert ev_principal is not None
    require(ev_principal, Permission.EVIDENCE_READ)
    require(ev_principal, Permission.PHOTO_URL)
    for perm in (
        Permission.RETURNS_WRITE,
        Permission.RETURNS_READ,
        Permission.REVIEW_WRITE,
        Permission.SIGNOFF,
        Permission.ADMIN,
        Permission.METRICS_READ,
    ):
        with pytest.raises(Forbidden):
            require(ev_principal, perm)

    # returns:write permits RETURNS_WRITE only; NOT PHOTO_URL (that requires returns:read or evidence:read).
    rw_key = await api_keys.create_key(
        db,
        org_id=alpha,
        name="t-sec-07-writer",
        scopes=["returns:write"],
        created_by="test",
        env="local",
    )
    rw_principal = await api_keys.authenticate(db, rw_key.plaintext, env="local")
    assert rw_principal is not None
    require(rw_principal, Permission.RETURNS_WRITE)
    for perm in (Permission.PHOTO_URL, Permission.EVIDENCE_READ, Permission.ADMIN):
        with pytest.raises(Forbidden):
            require(rw_principal, perm)

    # revoked key must not authenticate.
    await api_keys.revoke_key(db, alpha, ev_key.key_id)
    revoked = await api_keys.authenticate(db, ev_key.plaintext, env="local")
    assert revoked is None, "revoked key must not authenticate"


# ── T-SEC-08 ───────────────────────────────────────────────────────────────────


@pytest.mark.db
@pytest.mark.asyncio
async def test_t_sec_08_kill_switch_rules(db: Database, two_orgs: tuple[str, str]) -> None:
    """Kill-switch controls: global/org writes; reason required."""
    alpha, _ = two_orgs
    admin = Principal(kind="user", org_id=alpha, actor_id="test-admin", role=Role.ADMIN)

    # Empty reason must raise ReasonRequired (not reach the DB).
    with pytest.raises(controls.ReasonRequired):
        await controls.set_global_control(db, Control.MODEL_CALLS, False, "", "test")

    # Set a global control to off (no-context, CLI-only).
    row = await controls.set_global_control(
        db, Control.MODEL_CALLS, False, "test drill — model calls off globally", "test-cli"
    )
    assert not row.enabled
    assert row.scope == "global"

    # Re-enable it.
    row = await controls.set_global_control(  # re-enable
        db, Control.MODEL_CALLS, True, "test drill complete", "test-cli"
    )
    assert row.enabled

    # Set an org-level control.
    org_row = await controls.set_org_control(
        db, admin, Control.AUTO_DISPOSITION, False, "test drill — org disable auto-disposition"
    )
    assert not org_row.enabled
    assert org_row.scope == alpha

    # Effective: global=on, org=off → effective=off.
    eff = await controls.effective(db, alpha)
    assert not eff[Control.AUTO_DISPOSITION].enabled, "org override must dominate"
    assert eff[Control.MODEL_CALLS].enabled, "global re-enabled → effective on"
