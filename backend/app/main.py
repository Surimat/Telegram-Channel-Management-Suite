"""FastAPI application factory and entry point.

Run locally with:

    python -m backend.app.main
    # or (auto-reload needs watchfiles: pip install "uvicorn[standard]")
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
from backend.app.db.migrate import upgrade_database
from backend.app.db.session import dispose_engine
from backend.app.scheduler.handlers import register_handlers
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

    # Apply versioned database migrations (replaces create_all). Safe on fresh
    # installs (creates schema), existing create_all installs (is stamped at
    # head, no table touched) and upgrades (pre-migration backup + transaction).
    migration = await upgrade_database()
    if migration.state == "failed":
        logger.error("Database migration did not complete: %s", migration.error)
    elif migration.applied:
        logger.info("Applied %d database migration(s)", len(migration.applied))

    # Register the manager bot from .env/settings if configured (best effort).
    with contextlib.suppress(Exception):
        from backend.app.db.session import session_scope
        from backend.app.services.bot_service import BotService

        async with session_scope() as session:
            await BotService(session).ensure_manager_bot()

    # Seed editable reaction rules + recover reaction jobs left running.
    with contextlib.suppress(Exception):
        from backend.app.db.session import session_scope
        from backend.app.services.reaction_service import ReactionService

        async with session_scope() as session:
            service = ReactionService(session)
            await service.ensure_default_rules()
            await service.ensure_default_profile()
            recovered = await service.recover()
            if recovered:
                logger.info("Recovered %d reaction job(s) after restart", recovered)

    # Reset user accounts stuck mid-authorization after a restart (PHASE 4).
    with contextlib.suppress(Exception):
        from backend.app.db.session import session_scope
        from backend.app.services.session_service import SessionService

        async with session_scope() as session:
            reset = await SessionService(session).recover()
            if reset:
                logger.info("Reset %d unfinished account authorization(s)", reset)

    # Safely pause audience scans interrupted by a restart (PHASE 5).
    with contextlib.suppress(Exception):
        from backend.app.db.session import session_scope
        from backend.app.services.audience_service import AudienceService

        async with session_scope() as session:
            paused = await AudienceService(session).recover()
            if paused:
                logger.info("Paused %d interrupted audience scan(s) after restart", paused)

    # Pause invite runs interrupted by a restart — never resume a bulk action
    # silently; the operator resumes explicitly (PHASE 6).
    with contextlib.suppress(Exception):
        from backend.app.db.session import session_scope
        from backend.app.services.invite_service import InviteService

        async with session_scope() as session:
            paused = await InviteService(session).recover()
            if paused:
                logger.info("Paused %d interrupted invite run(s) after restart", paused)

    # Seed the recurring Content Studio posting tick (v1.2). The handler
    # re-schedules itself every POSTING_TICK_SECONDS, so a publication scheduled
    # for later still fires without a restart.
    with contextlib.suppress(Exception):
        from backend.app.db.session import session_scope
        from backend.app.scheduler.handlers import POSTING_TICK_SECONDS
        from backend.app.services.posting_service import POSTING_JOB_KIND
        from backend.app.services.queue_service import QueueService

        async with session_scope() as session:
            await QueueService(session).ensure_periodic(
                POSTING_JOB_KIND, interval_seconds=POSTING_TICK_SECONDS
            )

    # Seed the LAN Mesh maintenance tick. It is a cheap no-op while the mesh is
    # disabled, so the recurring job always exists and enabling the mesh needs no
    # restart. It re-schedules itself like the posting tick.
    with contextlib.suppress(Exception):
        from backend.app.db.session import session_scope
        from backend.app.scheduler.handlers import MESH_TICK_JOB_KIND
        from backend.app.services.queue_service import QueueService

        async with session_scope() as session:
            await QueueService(session).ensure_periodic(
                MESH_TICK_JOB_KIND, interval_seconds=max(5, settings.mesh_tick_interval)
            )

    scheduler: Scheduler | None = None
    if settings.scheduler_enabled:
        scheduler = Scheduler()
        register_handlers(scheduler)
        app.state.scheduler = scheduler
        await scheduler.start()

    # Manager-bot runtime: short-poll command loop + notification forwarding.
    # Optional and offline-tolerant; it never blocks the scheduler. In a LAN mesh
    # only the elected coordinator owns the Telegram pollers, so two computers on
    # the same bot token never poll (and double-process updates) at the same time.
    manager_runtime = None
    pollers_owned = True
    if settings.mesh_enabled and settings.mesh_mode != "standalone":
        with contextlib.suppress(Exception):
            from backend.app.db.session import session_scope
            from backend.app.mesh.service import MeshService

            async with session_scope() as session:
                pollers_owned = await MeshService(session).owns_telegram_pollers()
    if settings.manager_runtime_enabled and pollers_owned:
        from backend.app.manager.runtime import ManagerBotRuntime

        manager_runtime = ManagerBotRuntime(
            poll_interval=settings.manager_runtime_poll_interval
        )
        app.state.manager_runtime = manager_runtime
        with contextlib.suppress(Exception):
            await manager_runtime.start()

    # Announce startup (best effort; delivered on the next runtime poll).
    with contextlib.suppress(Exception):
        from backend.app.manager.bus import CATEGORY_SYSTEM, publish

        publish(
            category=CATEGORY_SYSTEM,
            event_key="app.started",
            message=f"Приложение запущено (версия {__version__}).",
            level="INFO",
        )

    try:
        yield
    finally:
        # Announce shutdown (best effort) before the event loop and DB go away.
        with contextlib.suppress(Exception):
            from backend.app.manager.bus import CATEGORY_SYSTEM, get_notification_bus

            if not get_notification_bus().empty():
                # Flush what we can synchronously via a short-lived provider.
                from backend.app.db.session import session_scope
                from backend.app.manager.service import ManagerBotService

                async with session_scope() as session:
                    service = ManagerBotService(session)
                    provider = await service.manager_provider()
                    if provider is not None:
                        try:
                            await service.deliver_pending(provider)
                        finally:
                            await provider.close()
            from backend.app.manager.bus import publish

            publish(
                category=CATEGORY_SYSTEM,
                event_key="app.stopped",
                message="Приложение остановлено.",
                level="INFO",
            )
        if manager_runtime is not None:
            with contextlib.suppress(Exception):
                await manager_runtime.stop()
        if scheduler is not None:
            await scheduler.stop()
        with contextlib.suppress(Exception):
            from backend.app.ai.inference import shutdown_executor

            shutdown_executor()
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

    # Owner guard is added first so CORS stays outermost (preflight responses
    # still receive CORS headers). While no owner profile exists, or protection
    # is off, the guard is a pass-through (local-first, D-105).
    from backend.app.api.owner_guard import OwnerGuardMiddleware

    app.add_middleware(OwnerGuardMiddleware)
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
