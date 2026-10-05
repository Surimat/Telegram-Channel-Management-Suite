"""Product router: backup destinations, promotion wizard and auto-update.

These are the "make it a product" surfaces: where a backup is delivered, the
guided first-run wizard, and the conservative update flow. Nothing here needs a
user session and nothing exposes credentials.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import (
    get_destination_service,
    get_promotion_service,
    get_update_service,
)
from backend.app.api.errors import ApiError
from backend.app.api.schemas.product import (
    DeliveryResultOut,
    DestinationIn,
    DestinationListOut,
    DestinationOut,
    DestinationUpdate,
    PresetOut,
    UpdateStatusOut,
    UpdateToggleIn,
    WizardPresetIn,
    WizardStateOut,
    WizardStepIn,
)
from backend.app.db.models.backup_destination import DestinationKind
from backend.app.services.destination_service import (
    DestinationService,
    DestinationServiceError,
    DestinationView,
    provider_infos,
)
from backend.app.services.promotion_service import PromotionService, preset_list
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


# --- promotion wizard -------------------------------------------------------
@router.get("/promotion/presets", response_model=list[PresetOut])
async def list_presets() -> list[PresetOut]:
    return [PresetOut(**p) for p in preset_list()]


@router.get("/promotion", response_model=WizardStateOut)
async def wizard_state(
    service: PromotionService = Depends(get_promotion_service),
) -> WizardStateOut:
    return _wizard_out(await service.state())


@router.post("/promotion/preset", response_model=WizardStateOut)
async def set_preset(
    payload: WizardPresetIn,
    service: PromotionService = Depends(get_promotion_service),
) -> WizardStateOut:
    return _wizard_out(await service.set_preset(payload.preset))


@router.post("/promotion/step", response_model=WizardStateOut)
async def set_step(
    payload: WizardStepIn,
    service: PromotionService = Depends(get_promotion_service),
) -> WizardStateOut:
    return _wizard_out(await service.set_step(payload.step))


@router.post("/promotion/finish", response_model=WizardStateOut)
async def finish_wizard(
    service: PromotionService = Depends(get_promotion_service),
) -> WizardStateOut:
    return _wizard_out(await service.finish())


@router.post("/promotion/dismiss", response_model=WizardStateOut)
async def dismiss_wizard(
    service: PromotionService = Depends(get_promotion_service),
) -> WizardStateOut:
    return _wizard_out(await service.dismiss())


def _wizard_out(state) -> WizardStateOut:  # type: ignore[no-untyped-def]
    return WizardStateOut(
        preset=state.preset,
        preset_title=state.preset_title,
        preset_description=state.preset_description,
        has_session=state.has_session,
        mode=state.mode,
        completed=state.completed,
        dismissed=state.dismissed,
        current_step=state.current_step,
        completed_steps=state.completed_steps,
        total_steps=state.total_steps,
        session_optional_note=state.session_optional_note,
        session_risk_note=state.session_risk_note,
        steps=[
            {
                "key": s.key,
                "title": s.title,
                "description": s.description,
                "status": s.status,
                "status_title": s.status_title,
                "how_to_fix": s.how_to_fix,
                "route": s.route,
                "requires_session": s.requires_session,
            }
            for s in state.steps
        ],
    )


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
