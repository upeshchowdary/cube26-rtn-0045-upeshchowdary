"""FastAPI application (§15). Business logic lives in the service modules; routes only translate HTTP.

Start-up is fail-safe: the pool is opened and the boot check runs before the app serves anything. If the
database role can bypass row-level security, start-up raises and the process refuses to serve.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

from returns_manager import __version__
from returns_manager.api import problems
from returns_manager.api.deps import Services, ServicesDep
from returns_manager.api.routes import intake as intake_routes
from returns_manager.api.routes import security as security_routes
from returns_manager.config import Settings, get_settings
from returns_manager.db.pool import Database
from returns_manager.ids import new_id
from returns_manager.security.auth_jwt import JwtVerifier
from returns_manager.storage.photos import PhotoStorage

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.require("database_url")
        assert settings.database_url is not None
        db = Database(settings.database_url.get_secret_value())
        await db.open()  # runs the boot check; raises UnsafeDatabaseRole under a bypass role
        jwt = JwtVerifier(settings) if (settings.supabase_jwks_url or settings.supabase_jwt_secret) else None
        storage = PhotoStorage(settings) if settings.supabase_url else None
        app.state.services = Services(settings=settings, db=db, jwt=jwt, storage=storage)
        try:
            yield
        finally:
            await db.close()

    app = FastAPI(
        title="Returns Manager API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    problems.install(app)

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        incoming = request.headers.get("x-request-id")
        rid = incoming if incoming and _REQUEST_ID_RE.match(incoming) else new_id()
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    class Health(BaseModel):
        status: str
        version: str

    @app.get("/health", response_model=Health)
    async def health() -> Health:
        """Liveness only; touches no dependency."""
        return Health(status="ok", version=__version__)

    class Ready(BaseModel):
        ready: bool
        checks: dict[str, Any]

    @app.get("/ready", response_model=Ready)
    async def ready(svc: ServicesDep, response: Response) -> Ready:
        checks: dict[str, Any] = {"database_role_non_bypass": svc.db.role_name is not None}
        try:
            async with svc.db.transaction(None) as conn:
                await conn.execute("SELECT 1")
            checks["database"] = True
        except Exception:
            checks["database"] = False
        checks["storage"] = await svc.storage.ping() if svc.storage else False
        checks["models"] = "not checked until phase P5"
        ok = bool(checks["database"] and checks["database_role_non_bypass"] and checks["storage"])
        response.status_code = 200 if ok else 503
        return Ready(ready=ok, checks=checks)

    app.include_router(security_routes.router)
    app.include_router(intake_routes.router)
    return app
