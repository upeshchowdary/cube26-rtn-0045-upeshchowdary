"""Request dependencies: the calling Principal (JWT or API key) and shared services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from returns_manager.config import Settings
from returns_manager.db.pool import Database
from returns_manager.security import api_keys
from returns_manager.security.auth_jwt import JwtVerifier, user_principal
from returns_manager.security.roles import Principal, Unauthenticated
from returns_manager.storage.photos import PhotoStorage


@dataclass
class Services:
    settings: Settings
    db: Database
    jwt: JwtVerifier | None
    storage: PhotoStorage | None


def services(request: Request) -> Services:
    svc: Services = request.app.state.services
    return svc


async def principal(
    request: Request,
    svc: Annotated[Services, Depends(services)],
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    x_org_id: Annotated[str | None, Header()] = None,
) -> Principal:
    if authorization and x_api_key:
        raise Unauthenticated("send either a bearer token or an API key, not both")
    if x_api_key:
        p = await api_keys.authenticate(svc.db, x_api_key, env=svc.settings.rm_env)
        if p is None:
            raise Unauthenticated("invalid API key")
        return p
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise Unauthenticated("expected 'Authorization: Bearer <token>'")
        if svc.jwt is None:
            raise Unauthenticated("user tokens are not configured on this deployment")
        verified = await svc.jwt.verify(token.strip())
        return await user_principal(svc.db, verified, x_org_id)
    raise Unauthenticated("missing credentials")


PrincipalDep = Annotated[Principal, Depends(principal)]
ServicesDep = Annotated[Services, Depends(services)]
