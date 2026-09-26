"""§6.6 authorization matrix and API-key format (no database)."""

from __future__ import annotations

import pytest

from returns_manager.security.api_keys import generate, hash_key, parse_scopes
from returns_manager.security.roles import Forbidden, Permission, Principal, Role, Scope, require


def user(role: Role) -> Principal:
    return Principal(kind="user", org_id="org_demo_alpha", actor_id="u", role=role)


def key(*scopes: Scope) -> Principal:
    return Principal(kind="api_key", org_id="org_demo_alpha", actor_id="k", scopes=frozenset(scopes))


@pytest.mark.parametrize(
    ("principal", "allowed", "denied"),
    [
        (
            user(Role.OPERATOR),
            {Permission.RETURNS_WRITE, Permission.PHOTO_URL},
            {Permission.REVIEW_WRITE, Permission.SIGNOFF, Permission.ADMIN},
        ),
        (
            user(Role.REVIEWER),
            {Permission.REVIEW_WRITE, Permission.SIGNOFF, Permission.RETURNS_WRITE},
            {Permission.ADMIN},
        ),
        (user(Role.ADMIN), set(Permission), set()),
        # Recovery's key: evidence:read only.
        (
            key(Scope.EVIDENCE_READ),
            {Permission.EVIDENCE_READ, Permission.PHOTO_URL},
            {Permission.RETURNS_WRITE, Permission.RETURNS_READ, Permission.ADMIN, Permission.SIGNOFF},
        ),
        (key(Scope.RETURNS_WRITE), {Permission.RETURNS_WRITE}, {Permission.PHOTO_URL, Permission.ADMIN}),
        (key(Scope.ADMIN), set(Permission), set()),
    ],
)
def test_matrix(principal: Principal, allowed: set[Permission], denied: set[Permission]) -> None:
    for perm in allowed:
        require(principal, perm)
    for perm in denied:
        with pytest.raises(Forbidden):
            require(principal, perm)


def test_user_without_role_has_no_permissions() -> None:
    p = Principal(kind="user", org_id="org_demo_alpha", actor_id="u", role=None)
    assert p.permissions == frozenset()


def test_key_format_prefix_and_hash() -> None:
    plaintext, prefix = generate("local")
    assert plaintext.startswith("rmk_local_")
    random_part = plaintext.removeprefix("rmk_local_")
    assert len(random_part) == 40
    assert random_part.isalnum()
    assert prefix == random_part[:8]
    assert len(hash_key(plaintext)) == 32
    assert generate("local")[0] != plaintext


def test_scopes_are_validated() -> None:
    assert parse_scopes(["evidence:read", "evidence:read"]) == ("evidence:read",)
    with pytest.raises(ValueError, match=r"not a valid Scope|at least one scope"):
        parse_scopes(["evidence:write"])
    with pytest.raises(ValueError, match="at least one scope"):
        parse_scopes([])
