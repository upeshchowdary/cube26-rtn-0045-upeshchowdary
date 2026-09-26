"""T-MCP-* tests for the read-only MCP server (Phase 10, §16).

These cover the gap found in a P10 re-verification: the MCP tools originally accepted
`org_id` as a plain caller-supplied argument with no authentication, letting any MCP
client read any organization's evidence. They now derive `org_id` exclusively from an
authenticated API key (mirroring the REST `PrincipalDep` pattern), and never accept it
as a tool parameter.

  T-MCP-01  authenticate_bearer_token rejects a missing/malformed Authorization header.
  T-MCP-02  authenticate_bearer_token rejects an unknown/invalid API key.
  T-MCP-03  authenticate_bearer_token rejects a valid key lacking evidence:read.
  T-MCP-04  authenticate_bearer_token accepts a valid evidence:read key and returns its org.
  T-MCP-05  Building the server registers exactly the four read-only tools from §16.
  T-MCP-06  A tool has no `org_id` parameter: a client cannot smuggle a target org in.
  T-MCP-07  get_return_evidence, called under org A's context, cannot see org B's unit.
  T-MCP-08  Calling a tool with no principal in context fails loudly (auth wiring bug,
            not a silent cross-tenant read).
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from returns_manager.db.pool import Database
from returns_manager.security import api_keys
from returns_manager.security.roles import Forbidden, Unauthenticated

pytestmark = pytest.mark.db


def _fresh_org() -> str:
    return f"org_t{uuid.uuid4().hex[:12]}"


@pytest_asyncio.fixture()
async def two_orgs(db: Database) -> tuple[str, str]:
    alpha, bravo = _fresh_org(), _fresh_org()
    for org_id in (alpha, bravo):
        async with db.transaction(org_id) as conn:
            await conn.execute(
                "INSERT INTO rm.organizations (org_id, name) VALUES (%s, %s)",
                (org_id, f"Test org {org_id}"),
            )
    return alpha, bravo


@pytest_asyncio.fixture()
async def mcp_server(db: Database) -> AsyncIterator[object]:
    """Build a real MCPServer instance against the test database."""
    pytest.importorskip("mcp", reason="the 'mcp' package is required for the MCP server")
    from returns_manager.config import get_settings
    from returns_manager.mcp_server import _build_mcp_server

    settings = get_settings()
    mcp = _build_mcp_server(settings)
    # Reuse the already-open, already-migrated test pool instead of opening a second one.
    mcp.rm_db = db
    yield mcp


# ── T-MCP-01..04: authenticate_bearer_token ───────────────────────────────────


@pytest.mark.asyncio
async def test_t_mcp_01_rejects_missing_or_malformed_header(db: Database) -> None:
    from returns_manager.mcp_server import authenticate_bearer_token

    for header in (None, "", "Basic abc123", "Bearer", "Bearer   "):
        with pytest.raises(Unauthenticated):
            await authenticate_bearer_token(db, header, env="test")


@pytest.mark.asyncio
async def test_t_mcp_02_rejects_unknown_key(db: Database) -> None:
    from returns_manager.mcp_server import authenticate_bearer_token

    with pytest.raises(Unauthenticated):
        await authenticate_bearer_token(db, "Bearer rmk_test_doesnotexist00000000000000000000", env="test")


@pytest.mark.asyncio
async def test_t_mcp_03_rejects_key_without_evidence_read(db: Database, two_orgs: tuple[str, str]) -> None:
    from returns_manager.mcp_server import authenticate_bearer_token

    alpha, _ = two_orgs
    key = await api_keys.create_key(
        db, org_id=alpha, name="t-mcp-03", scopes=["returns:write"], created_by="test", env="test"
    )
    with pytest.raises(Forbidden):
        await authenticate_bearer_token(db, f"Bearer {key.plaintext}", env="test")


@pytest.mark.asyncio
async def test_t_mcp_04_accepts_valid_evidence_read_key(db: Database, two_orgs: tuple[str, str]) -> None:
    from returns_manager.mcp_server import authenticate_bearer_token

    alpha, _ = two_orgs
    key = await api_keys.create_key(
        db, org_id=alpha, name="t-mcp-04", scopes=["evidence:read"], created_by="test", env="test"
    )
    principal = await authenticate_bearer_token(db, f"Bearer {key.plaintext}", env="test")
    assert principal.org_id == alpha
    assert principal.kind == "api_key"


# ── T-MCP-05..06: tool registration and signatures ────────────────────────────


@pytest.mark.asyncio
async def test_t_mcp_05_registers_four_read_only_tools(mcp_server: object) -> None:
    tools = mcp_server._tool_manager._tools  # type: ignore[attr-defined]
    assert set(tools.keys()) == {
        "get_return_evidence",
        "list_return_evidence",
        "verify_return_chain",
        "explain_return_decision",
    }


@pytest.mark.asyncio
async def test_t_mcp_06_no_tool_accepts_org_id(mcp_server: object) -> None:
    tools = mcp_server._tool_manager._tools  # type: ignore[attr-defined]
    for name, tool in tools.items():
        fn = tool.fn
        params = inspect.signature(fn).parameters
        assert "org_id" not in params, f"tool {name!r} must not accept org_id from the caller"


# ── T-MCP-07..08: tenancy is enforced by context, not by argument ─────────────


@pytest.mark.asyncio
async def test_t_mcp_07_get_return_evidence_is_scoped_to_context_org(
    mcp_server: object, two_orgs: tuple[str, str]
) -> None:
    from returns_manager.mcp_server import _principal_var
    from returns_manager.security.roles import Principal, Scope

    alpha, bravo = two_orgs
    tools = mcp_server._tool_manager._tools  # type: ignore[attr-defined]
    get_return_evidence = tools["get_return_evidence"].fn

    # No record exists for either org yet; the important thing is which org_id
    # reaches the service layer, so patch get_evidence_document to capture it.
    seen: dict[str, str] = {}

    async def fake_get_evidence_document(pool: object, *, org_id: str, unit_id: str, **kw: object) -> None:
        seen["org_id"] = org_id
        seen["unit_id"] = unit_id
        return None

    import returns_manager.contract.service as svc

    monkey_original = svc.get_evidence_document
    svc.get_evidence_document = fake_get_evidence_document  # type: ignore[assignment]
    try:
        alpha_principal = Principal(
            kind="api_key", org_id=alpha, actor_id="k1", scopes=frozenset({Scope.EVIDENCE_READ})
        )
        token = _principal_var.set(alpha_principal)
        try:
            await get_return_evidence(unit_id="UNIT-DOES-NOT-EXIST")
        finally:
            _principal_var.reset(token)
        assert seen["org_id"] == alpha
        assert seen["org_id"] != bravo
    finally:
        svc.get_evidence_document = monkey_original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_t_mcp_08_tool_call_without_principal_fails_loudly(mcp_server: object) -> None:
    tools = mcp_server._tool_manager._tools  # type: ignore[attr-defined]
    get_return_evidence = tools["get_return_evidence"].fn
    with pytest.raises(RuntimeError, match="no authenticated principal"):
        await get_return_evidence(unit_id="UNIT-0001")
