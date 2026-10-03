"""FastAPI application factory and entry point.

Run locally with:

    python -m backend.app.main
    # or
    uvicorn backend.app.main:app --reload
"""

from __future__ import annotations

import contextlib
import json
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


def _register_handlers(scheduler: Scheduler) -> None:
    """Register durable-queue job handlers (PHASE 3/5)."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.app.db.models.job import Job
    from backend.app.services.audience_service import SCAN_JOB_KIND, AudienceService
    from backend.app.services.invite_service import INVITE_JOB_KIND, InviteService
    from backend.app.services.reaction_service import REACTION_JOB_KIND, ReactionService

    async def handle_reaction(session: AsyncSession, job: Job) -> None:
        payload = json.loads(job.payload or "{}")
        reaction_job_id = payload.get("reaction_job_id")
        if reaction_job_id:
            await ReactionService(session).execute_reaction_job(reaction_job_id)

    async def handle_scan(session: AsyncSession, job: Job) -> None:
        # The service streams one bounded chunk per tick, committing progress so
        # an interrupted scan can resume (decision D-028).
        await AudienceService(session).run_scan_chunk()

    async def handle_invite(session: AsyncSession, job: Job) -> None:
        # One bounded batch per tick. While work remains, re-schedule a follow-up
        # job at the next due time so per-account delays are honoured and the run
        # stays restart-safe (decision D-008).
        payload = json.loads(job.payload or "{}")
        invite_job_id = payload.get("invite_job_id")
        if not invite_job_id:
            return
        from datetime import timedelta

        from backend.app.db.base import utcnow
        from backend.app.services.queue_service import QueueService

        action, delay = await InviteService(session).run_tick(invite_job_id)
        if action == "more":
            await QueueService(session).enqueue(
                kind=INVITE_JOB_KIND,
                payload={"invite_job_id": invite_job_id},
                scheduled_at=utcnow() + timedelta(seconds=delay),
                group_key=invite_job_id,
                max_attempts=1,
            )

    scheduler.register(REACTION_JOB_KIND, handle_reaction)
    scheduler.register(SCAN_JOB_KIND, handle_scan)
    scheduler.register(INVITE_JOB_KIND, handle_invite)


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

    scheduler: Scheduler | None = None
    if settings.scheduler_enabled:
        scheduler = Scheduler()
        _register_handlers(scheduler)
        app.state.scheduler = scheduler
        await scheduler.start()

    # Manager-bot runtime: short-poll command loop + notification forwarding.
    # Optional and offline-tolerant; it never blocks the scheduler.
    manager_runtime = None
    if settings.manager_runtime_enabled:
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
