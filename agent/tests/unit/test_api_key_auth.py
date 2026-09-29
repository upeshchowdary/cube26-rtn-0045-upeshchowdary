"""X-API-Key authentication has no shortcut: unknown or malformed keys get 401 in every RM_ENV (A13).

No database: a fake `Database` answers `rm.resolve_api_key` with "no such key", so a well-formed
but unknown key reaches the real lookup and is still refused.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from returns_manager.api import problems
from returns_manager.api.deps import Services, principal
from returns_manager.security.roles import Principal


class _NoRowCursor:
    async def fetchone(self) -> None:
        return None


class _Conn:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def execute(self, sql: str, params: Any = None) -> _NoRowCursor:
        self._calls.append(sql)
        return _NoRowCursor()


class _FakeDb:
    """Every key lookup finds nothing."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @asynccontextmanager
    async def transaction(self, org_id: str | None):  # type: ignore[no-untyped-def]
        yield _Conn(self.calls)


class _BrokenDb:
    """The database is down: lookups raise."""

    @asynccontextmanager
    async def transaction(self, org_id: str | None):  # type: ignore[no-untyped-def]
        raise ConnectionError("db unreachable")
        yield  # pragma: no cover


@dataclass
class _Settings:
    rm_env: str


def _client(env: str, db: Any) -> TestClient:
    app = FastAPI()
    problems.install(app)
    app.state.services = Services(settings=_Settings(rm_env=env), db=db, jwt=None, storage=None)  # type: ignore[arg-type]

    @app.get("/whoami")
    async def whoami(p: Annotated[Principal, Depends(principal)]) -> dict[str, str]:
        return {"org_id": p.org_id, "actor_id": p.actor_id}

    return TestClient(app, raise_server_exceptions=False)


ENVS = ("local", "test", "demo")
# Former backdoor prefixes (any string starting rmk_local_/rmk_demo_ used to get full admin),
# plus a malformed key and well-formed-but-unknown keys for every env.
PRESENTED = (
    "rmk_local_anything",
    "rmk_demo_anything",
    "rmk_local_",
    "not-a-key",
    "rmk_local_" + "A" * 40,
    "rmk_demo_" + "B" * 40,
    "rmk_test_" + "C" * 40,
)


@pytest.mark.parametrize("env", ENVS)
@pytest.mark.parametrize("key", PRESENTED)
def test_unknown_or_malformed_api_key_is_401_in_every_env(env: str, key: str) -> None:
    resp = _client(env, _FakeDb()).get("/whoami", headers={"X-API-Key": key})
    assert resp.status_code == 401, resp.text
    assert "org_demo_alpha" not in resp.text


def test_well_formed_key_is_looked_up_not_waved_through() -> None:
    db = _FakeDb()
    resp = _client("local", db).get("/whoami", headers={"X-API-Key": "rmk_local_" + "A" * 40})
    assert resp.status_code == 401
    assert any("resolve_api_key" in sql for sql in db.calls)


@pytest.mark.parametrize("env", ENVS)
def test_db_failure_during_key_lookup_never_authenticates(env: str) -> None:
    resp = _client(env, _BrokenDb()).get("/whoami", headers={"X-API-Key": "rmk_local_" + "A" * 40})
    assert resp.status_code != 200
    assert "local_demo_actor" not in resp.text
