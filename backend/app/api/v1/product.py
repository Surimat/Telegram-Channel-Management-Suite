"""Product router: backup destinations and auto-update.

These are the "make it a product" surfaces: where a backup is delivered and the
conservative update flow. Nothing here needs a user session and nothing exposes
credentials. (Onboarding lives in the single Setup Wizard, `/api/v1/setup-wizard`.)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import (
    get_destination_service,
    get_update_service,
)
from backend.app.api.errors import ApiError
from backend.app.api.schemas.product import (
    DeliveryResultOut,
    DestinationIn,
    DestinationListOut,
    DestinationOut,
    DestinationUpdate,
    UpdateStatusOut,
    UpdateToggleIn,
)
from backend.app.db.models.backup_destination import DestinationKind
from backend.app.services.destination_service import (
    DestinationService,
    DestinationServiceError,
    DestinationView,
    provider_infos,
)
from backend.app.services.update_service import UpdateService, status_to_dict

router = APIRouter(tags=["product"])


def _dest_out(view: DestinationView) -> DestinationOut:
    return DestinationOut(
        id=view.id,
        kind=view.kind,
        title=view.title,
        label=view.label,
        enabled=view.enabled,
        status=view.status,
        account_label=view.account_label,
        config=view.config,
        last_backup_at=view.last_backup_at,
        last_error=view.last_error,
        available_space=view.available_space,
    )


def _parse_kind(value: str) -> DestinationKind:
    try:
        return DestinationKind(value)
    except ValueError as exc:
        raise ApiError(
            422,
            "Неизвестное место хранения.",
            "Допустимо: local, google_drive, yandex_disk, telegram.",
        ) from exc


# --- destinations -----------------------------------------------------------
@router.get("/backup/destinations", response_model=DestinationListOut)
async def list_destinations(
    service: DestinationService = Depends(get_destination_service),
) -> DestinationListOut:
    await service.ensure_defaults()
    rows = await service.list_destinations()
    return DestinationListOut(
        items=[_dest_out(r) for r in rows],
        total=len(rows),
        available_kinds=provider_infos(),
    )


@router.post("/backup/destinations", response_model=DestinationOut, status_code=201)
async def add_destination(
    payload: DestinationIn,
    service: DestinationService = Depends(get_destination_service),
) -> DestinationOut:
    try:
        row = await service.add_destination(
            _parse_kind(payload.kind),
            label=payload.label,
            enabled=payload.enabled,
            config=payload.config,
            token=payload.token,
        )
    except DestinationServiceError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _dest_out(service._view(row))


@router.patch("/backup/destinations/{destination_id}", response_model=DestinationOut)
async def update_destination(
    destination_id: str,
    payload: DestinationUpdate,
    service: DestinationService = Depends(get_destination_service),
) -> DestinationOut:
    try:
        row = await service.update_destination(
            destination_id,
            enabled=payload.enabled,
            label=payload.label,
            config=payload.config,
            token=payload.token,
        )
    except DestinationServiceError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _dest_out(service._view(row))


@router.post("/backup/destinations/{destination_id}/check", response_model=DestinationOut)
async def check_destination(
    destination_id: str,
    service: DestinationService = Depends(get_destination_service),
) -> DestinationOut:
    try:
        view = await service.check(destination_id)
    except DestinationServiceError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return _dest_out(view)


@router.delete("/backup/destinations/{destination_id}")
async def delete_destination(
    destination_id: str,
    service: DestinationService = Depends(get_destination_service),
) -> dict[str, bool]:
    try:
        await service.delete_destination(destination_id)
    except DestinationServiceError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return {"deleted": True}


@router.post("/backup/destinations/deliver", response_model=list[DeliveryResultOut])
async def deliver_to_destinations(
    service: DestinationService = Depends(get_destination_service),
) -> list[DeliveryResultOut]:
    # Re-send the newest local backup to every enabled destination.
    from backend.app.services.backup_service import BackupService

    backups = BackupService(service.session).list_backups()
    if not backups:
        raise ApiError(
            404,
            "Резервных копий пока нет.",
            "Создайте копию в разделе «Резервные копии».",
        )
    newest = backups[0]
    path = service.settings.resolve_backup_dir() / newest.filename
    results = await service.deliver(
        newest.filename, path.read_bytes(), caption="Резервная копия"
    )
    return [
        DeliveryResultOut(
            destination_id=r.destination_id, kind=r.kind, ok=r.ok, message=r.message
        )
        for r in results
    ]


# --- auto update ------------------------------------------------------------
@router.get("/update", response_model=UpdateStatusOut)
async def update_status(
    service: UpdateService = Depends(get_update_service),
) -> UpdateStatusOut:
    return UpdateStatusOut(**status_to_dict(await service.status()))


@router.post("/update/enabled", response_model=UpdateStatusOut)
async def set_update_enabled(
    payload: UpdateToggleIn,
    service: UpdateService = Depends(get_update_service),
) -> UpdateStatusOut:
    return UpdateStatusOut(**status_to_dict(await service.set_enabled(payload.enabled)))


@router.post("/update/check", response_model=UpdateStatusOut)
async def check_update(
    service: UpdateService = Depends(get_update_service),
) -> UpdateStatusOut:
    return UpdateStatusOut(**status_to_dict(await service.check()))


@router.post("/update/download", response_model=UpdateStatusOut)
async def download_update(
    service: UpdateService = Depends(get_update_service),
) -> UpdateStatusOut:
    return UpdateStatusOut(**status_to_dict(await service.download()))
