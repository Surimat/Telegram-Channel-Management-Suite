"""Diagnostics router: system state, safe maintenance actions, redacted report.

Everything here is owner-facing and safe by default:

* ``GET /diagnostics`` — one explained status row per subsystem.
* ``GET /diagnostics/actions`` — the safe maintenance actions and their state.
* ``POST /diagnostics/actions/{key}`` — run a safe, non-destructive action.
* ``GET /diagnostics/report?format=json|txt|zip`` — a **redacted** report file
  that contains no tokens, api_hash/api_id, session data, phone numbers,
  passwords or database contents.

The report is redacted and re-scanned server-side before it is returned; if the
safety scan is unsure, no file is produced.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from backend.app.api.deps import get_diagnostics_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.diagnostics import (
    DiagnosticsReport,
    MaintenanceAction,
    MaintenanceResult,
    ReportFormat,
)
from backend.app.services.diagnostics_service import DiagnosticsError, DiagnosticsService

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("", response_model=DiagnosticsReport)
async def diagnostics(
    request: Request,
    service: DiagnosticsService = Depends(get_diagnostics_service),
) -> DiagnosticsReport:
    return await service.collect(request.app.state)


@router.get("/actions", response_model=list[MaintenanceAction])
async def list_actions(
    request: Request,
    service: DiagnosticsService = Depends(get_diagnostics_service),
) -> list[MaintenanceAction]:
    return service.list_actions(request.app.state)


@router.get("/report/formats", response_model=ReportFormat)
async def report_formats() -> ReportFormat:
    return ReportFormat()


@router.post("/actions/{key}", response_model=MaintenanceResult)
async def run_action(
    key: str,
    request: Request,
    service: DiagnosticsService = Depends(get_diagnostics_service),
) -> MaintenanceResult:
    return await service.run_action(key, request.app.state)


@router.get("/report")
async def download_report(
    request: Request,
    format: str = Query(default="json", pattern="^(json|txt|zip)$"),
    service: DiagnosticsService = Depends(get_diagnostics_service),
) -> Response:
    try:
        content, filename, media_type = await service.build_report(format, request.app.state)
    except DiagnosticsError as exc:
        raise ApiError(500, str(exc), "Повторите попытку позже.") from exc
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Diagnostics-Redacted": "true",
        "Cache-Control": "no-store",
    }
    return Response(content=content, media_type=media_type, headers=headers)


__all__ = ["router"]
