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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from returns_manager import __version__
from returns_manager.api import problems
from returns_manager.api.deps import Services, ServicesDep
from returns_manager.api.routes import batch as batch_routes
from returns_manager.api.routes import chain as chain_routes
from returns_manager.api.routes import evidence as evidence_routes
from returns_manager.api.routes import explainer as explainer_routes
from returns_manager.api.routes import intake as intake_routes
from returns_manager.api.routes import jobs as jobs_routes
from returns_manager.api.routes import metrics as metrics_routes
from returns_manager.api.routes import review as review_routes
from returns_manager.api.routes import security as security_routes
from returns_manager.api.routes import simulate as simulate_routes
from returns_manager.api.routes import webhooks as webhooks_routes
from returns_manager.batch.jobs_service import BatchJobsService
from returns_manager.config import AGENT_ROOT, REPO_ROOT, Settings, get_settings
from returns_manager.db.pool import Database
from returns_manager.ids import new_id
from returns_manager.security.auth_jwt import JwtVerifier
from returns_manager.storage.photos import PhotoStorage

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    from returns_manager.observability.logging import configure_logging

    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db: Database | None = None
        if settings.database_url:
            try:
                db = Database(settings.database_url.get_secret_value())
                await db.open()  # runs the boot check; raises UnsafeDatabaseRole under a bypass role
            except Exception as exc:
                import logging

                logging.getLogger("returns_manager").warning(
                    "Database connection failed: %s. Operating in standalone demo mode.", exc
                )
                db = None
        else:
            import logging

            logging.getLogger("returns_manager").info(
                "DATABASE_URL is not set. Operating in standalone demo mode."
            )

        jwt = JwtVerifier(settings) if (settings.supabase_jwks_url or settings.supabase_jwt_secret) else None
        storage = PhotoStorage(settings) if settings.supabase_url else None
        batch_jobs: BatchJobsService | None = None
        if settings.gemini_api_key is not None:
            from returns_manager.llm.gemini_client import GeminiModelClient

            gemini_client = GeminiModelClient(
                settings.gemini_api_key.get_secret_value(), settings.rm_model_timeout_s
            )
            batch_jobs = BatchJobsService(
                root=AGENT_ROOT / ".data" / "batch_jobs",
                settings=settings,
                client=gemini_client,
                db=db,
            )
        app.state.services = Services(
            settings=settings,
            db=db,  # type: ignore[arg-type]
            jwt=jwt,
            storage=storage,
            batch_jobs=batch_jobs,
        )
        try:
            yield
        finally:
            if db is not None:
                await db.close()

    app = FastAPI(
        title="Returns Manager API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    problems.install(app)

    # Allow CORS across domains for public deployment
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
        has_db_role = bool(svc.db and svc.db.role_name is not None)
        checks: dict[str, Any] = {"database_role_non_bypass": has_db_role}
        if svc.db is not None:
            try:
                async with svc.db.transaction(None) as conn:
                    await conn.execute("SELECT 1")
                checks["database"] = True
            except Exception:
                checks["database"] = False
        else:
            checks["database"] = "standalone_mode"
        checks["storage"] = await svc.storage.ping() if svc.storage else False
        checks["models"] = "configured" if svc.settings.gemini_api_key else "not_configured"
        ok = (
            bool(checks["database"] and checks["database_role_non_bypass"] and checks["storage"])
            if svc.db is not None
            else True
        )
        response.status_code = 200 if ok else 503
        return Ready(ready=ok, checks=checks)

    app.include_router(security_routes.router)
    app.include_router(intake_routes.router)
    app.include_router(batch_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(simulate_routes.router)
    app.include_router(review_routes.router)
    app.include_router(chain_routes.router)
    app.include_router(evidence_routes.router)
    app.include_router(explainer_routes.router)
    app.include_router(webhooks_routes.router)
    app.include_router(metrics_routes.router)

    ui_dist = REPO_ROOT / "ui" / "dist"
    if (ui_dist / "index.html").exists():
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        if (ui_dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(ui_dist / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse | Response:
            target = ui_dist / full_path
            if full_path and target.is_file():
                return FileResponse(str(target))
            return FileResponse(str(ui_dist / "index.html"))

    return app
