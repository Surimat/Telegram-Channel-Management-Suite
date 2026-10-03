"""System router: status, setup wizard checks, info, graceful shutdown."""

from __future__ import annotations

import asyncio
import os
import signal

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app import __version__
from backend.app.api.schemas.system import SetupCheck, SystemStatus
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.services.system_service import SystemService

logger = get_logger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@router.get("/status", response_model=SystemStatus)
async def system_status(settings: Settings = Depends(get_settings)) -> SystemStatus:
    service = SystemService(settings)
    checks = await service.setup_checks()
    return SystemStatus(
        version=__version__,
        environment=settings.app_env,
        checks=[
            SetupCheck(
                key=c.key,
                title=c.title,
                status=c.status,
                meaning=c.meaning,
                how_to_fix=c.how_to_fix,
            )
            for c in checks
        ],
        overall=service.overall_status(checks),
    )


@router.get("/setup", response_model=list[SetupCheck])
async def setup_checks(settings: Settings = Depends(get_settings)) -> list[SetupCheck]:
    """Run all Setup Wizard checks (same data as status, list form)."""
    service = SystemService(settings)
    checks = await service.setup_checks()
    return [
        SetupCheck(
            key=c.key,
            title=c.title,
            status=c.status,
            meaning=c.meaning,
            how_to_fix=c.how_to_fix,
        )
        for c in checks
    ]


@router.get("/info")
async def system_info(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "version": __version__,
        "environment": settings.app_env,
        "language": settings.app_language,
        "scheduler_enabled": settings.scheduler_enabled,
        "ai_enabled": settings.ai_enabled,
    }


@router.post("/shutdown")
async def shutdown(request: Request) -> dict[str, str]:
    """Gracefully stop the local app (used by portable stop.bat).

    Only honoured for requests originating from the local machine, and only
    outside production, so a deployed instance can never be stopped remotely.
    """
    settings = get_settings()
    client_host = request.client.host if request.client else ""
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Остановка запрещена в рабочем режиме.")
    if client_host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="Остановка разрешена только локально.")
    logger.info("Graceful shutdown requested via local UI")

    def _signal() -> None:
        os.kill(os.getpid(), signal.SIGINT)

    # Defer the signal so this HTTP response can be delivered first.
    asyncio.get_running_loop().call_later(0.5, _signal)
    return {"status": "shutting_down"}
