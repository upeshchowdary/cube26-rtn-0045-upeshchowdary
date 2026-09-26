"""Shared test configuration."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

import pytest
import pytest_asyncio
from psycopg import AsyncConnection

from returns_manager.config import get_settings
from returns_manager.db.migrate import migrate
from returns_manager.db.pool import Database


def pytest_asyncio_loop_factories(
    config: Any, item: Any
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]] | None:
    # psycopg's async mode cannot run on Windows' default ProactorEventLoop.
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return None


def migrator_dsn() -> str:
    settings = get_settings()
    dsn = (
        (settings.database_migrator_url.get_secret_value() if settings.database_migrator_url else None)
        or os.environ.get("DATABASE_MIGRATOR_URL")
        or ""
    )
    if not dsn:
        pytest.skip("DATABASE_MIGRATOR_URL not set; run `npx supabase start` first")
    return dsn


def app_dsn() -> str:
    settings = get_settings()
    dsn = (
        (settings.database_url.get_secret_value() if settings.database_url else None)
        or os.environ.get("DATABASE_URL")
        or ""
    )
    if not dsn:
        pytest.skip("DATABASE_URL not set; run `npx supabase start` first")
    return dsn


@pytest_asyncio.fixture()
async def db() -> AsyncIterator[Database]:
    """Open rm_app_login database, run migrations (idempotent), yield the Database."""
    m_dsn = migrator_dsn()
    a_dsn = app_dsn()
    await migrate(m_dsn, a_dsn)
    database = Database(a_dsn)
    await database.open(check_role=True)
    yield database
    await database.close()


@pytest_asyncio.fixture()
async def quiet_queue(db: Database) -> AsyncIterator[set[str]]:
    """Park every job that exists before the test; yield; restore their schedule and leases exactly."""
    async with await AsyncConnection.connect(migrator_dsn(), autocommit=True) as admin:
        cur = await admin.execute(
            """SELECT job_id, next_attempt_at, lease_expires_at FROM rm.inspection_jobs
               WHERE status IN ('pending', 'failed_retryable', 'in_progress')"""
        )
        parked = await cur.fetchall()
        for job_id, _, _ in parked:
            await admin.execute(
                """UPDATE rm.inspection_jobs
                   SET next_attempt_at = now() + interval '1 day',
                       lease_expires_at = CASE WHEN lease_expires_at IS NULL THEN NULL
                                               ELSE now() + interval '1 day' END
                   WHERE job_id = %s""",
                (job_id,),
            )
        try:
            yield {r[0] for r in parked}
        finally:
            for job_id, next_at, lease_at in parked:
                await admin.execute(
                    "UPDATE rm.inspection_jobs SET next_attempt_at = %s, lease_expires_at = %s "
                    "WHERE job_id = %s",
                    (next_at, lease_at, job_id),
                )
