"""FastAPI application factory and entry point.

Run locally with:

    python -m backend.app.main
    # or
    uvicorn backend.app.main:app --reload
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from backend.app import __version__
from backend.app.api.errors import register_exception_handlers
from backend.app.api.v1.router import api_router
from backend.app.core import paths
from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger, setup_logging
from backend.app.core.security import validate_secret_key
from backend.app.db.session import dispose_engine, init_models
from backend.app.scheduler.scheduler import Scheduler

logger = get_logger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings)
    logger.info("Starting Telegram Channel Management Suite v%s", __version__)

    with contextlib.suppress(Exception):
        validate_secret_key(settings)

    # Ensure predictable runtime directories exist.
    for ensure in (
        paths.data_dir,
        paths.sessions_dir,
        paths.backups_dir,
        paths.logs_dir,
        paths.exports_dir,
    ):
        ensure()

    await init_models()

    # Register the manager bot from .env/settings if configured (best effort).
    with contextlib.suppress(Exception):
        from backend.app.db.session import session_scope
        from backend.app.services.bot_service import BotService

        async with session_scope() as session:
            await BotService(session).ensure_manager_bot()

    scheduler: Scheduler | None = None
    if settings.scheduler_enabled:
        scheduler = Scheduler()
        app.state.scheduler = scheduler
        await scheduler.start()

    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()
        await dispose_engine()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Telegram Channel Management Suite",
        version=__version__,
        description="Local-first Telegram channel management suite.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/health/deep", tags=["health"])
    async def health_deep() -> JSONResponse:
        from backend.app.db.session import session_scope
        from backend.app.services.system_service import SystemService

        service = SystemService(settings)
        async with session_scope() as session:
            checks = await service.setup_checks(session)
        overall = service.overall_status(checks)
        return JSONResponse(
            {
                "status": overall,
                "version": __version__,
                "checks": {c.key: c.status for c in checks},
            }
        )

    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """Serve the built SPA if present; provide an informative fallback."""
    static_dir = paths.static_dir()
    index_file = static_dir / "index.html"
    assets_dir = static_dir / "assets"

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, request: Request) -> object:
        # Never shadow API or health routes (they are registered above).
        if full_path.startswith(("api/", "health")):
            return JSONResponse(status_code=404, content={"error": {"code": "not_found"}})
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse(
            status_code=200,
            content={
                "status": "frontend_not_built",
                "message": (
                    "Веб-интерфейс ещё не собран. Выполните: "
                    "cd frontend && npm install && npm run build. "
                    "API доступен на /api/v1 и /docs."
                ),
                "version": __version__,
            },
        )


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "backend.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )


if __name__ == "__main__":
    main()
