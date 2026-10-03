"""Backup / restore router (PHASE 10).

Create, list, download, restore and delete backups, plus export/import of the
user-owned configuration. Responses never contain tokens, hashes, phones or
session contents.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response

from backend.app.api.deps import get_backup_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.backup import (
    BackupCreateIn,
    BackupEntryOut,
    BackupInfoOut,
    BackupListOut,
    ImportConfigOut,
    RestoreResultOut,
)
from backend.app.services.ai_help import human_size
from backend.app.services.backup_service import BackupError, BackupService

router = APIRouter(prefix="/backup", tags=["backup"])

_MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 64 MiB is plenty for a SQLite snapshot.


def _entry_out(entry) -> BackupEntryOut:  # type: ignore[no-untyped-def]
    return BackupEntryOut(
        filename=entry.filename,
        kind=entry.kind,
        created_at=entry.created_at,
        size_bytes=entry.size_bytes,
        size_human=human_size(entry.size_bytes),
        includes_sessions=entry.includes_sessions,
        version=entry.version,
    )


def _fail(exc: BackupError) -> ApiError:
    return ApiError(400, str(exc), "Проверьте выбранный файл и повторите попытку.")


@router.get("/info", response_model=BackupInfoOut)
async def info() -> BackupInfoOut:
    return BackupInfoOut(
        what_it_does=(
            "Резервная копия сохраняет базу данных приложения в один архив. "
            "Конфигурацию (правила, профили реакций, настройки) можно отдельно "
            "экспортировать и импортировать файлом."
        ),
        why=(
            "Копия защищает результаты работы: её можно восстановить на этом же "
            "или другом компьютере, а конфигурацию — перенести между установками."
        ),
        sessions_warning=(
            "Файлы сессий Telegram дают полный доступ к аккаунту, поэтому в копию "
            "они НЕ добавляются по умолчанию. Включайте это только для личной "
            "защищённой копии."
        ),
        safe_default="Обычная копия без сессий — безопасное значение по умолчанию.",
        excluded_tables=["bots", "user_sessions"],
    )


@router.get("", response_model=BackupListOut)
async def list_backups(
    service: BackupService = Depends(get_backup_service),
) -> BackupListOut:
    entries = service.list_backups()
    return BackupListOut(
        items=[_entry_out(e) for e in entries],
        total=len(entries),
        backup_dir=str(service.backup_dir()),
        retention=int(service.settings.backup_retention),
        include_sessions_default=bool(service.settings.backup_include_sessions),
    )


@router.post("", response_model=BackupEntryOut, status_code=201)
async def create_backup(
    payload: BackupCreateIn,
    service: BackupService = Depends(get_backup_service),
) -> BackupEntryOut:
    try:
        entry = await service.create_backup(
            include_sessions=payload.include_sessions, note=payload.note
        )
    except BackupError as exc:
        raise _fail(exc) from exc
    return _entry_out(entry)


@router.get("/download")
async def download_backup(
    filename: str = Query(min_length=1, max_length=200),
    service: BackupService = Depends(get_backup_service),
) -> Response:
    try:
        target = service._safe_member_path(filename)
    except BackupError as exc:
        raise _fail(exc) from exc
    if not target.is_file():
        raise ApiError(404, "Файл резервной копии не найден.")
    return Response(
        content=target.read_bytes(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore", response_model=RestoreResultOut)
async def restore_backup(
    filename: str = Query(min_length=1, max_length=200),
    service: BackupService = Depends(get_backup_service),
) -> RestoreResultOut:
    try:
        result = await service.restore_backup(filename)
    except BackupError as exc:
        raise _fail(exc) from exc
    return RestoreResultOut(
        restored=result.restored,
        source=result.source,
        safety_backup=result.safety_backup,
        includes_sessions=result.includes_sessions,
    )


@router.delete("/{filename}")
async def delete_backup(
    filename: str,
    service: BackupService = Depends(get_backup_service),
) -> dict[str, bool]:
    try:
        removed = service.delete_backup(filename)
    except BackupError as exc:
        raise _fail(exc) from exc
    if not removed:
        raise ApiError(404, "Файл резервной копии не найден.")
    return {"deleted": True}


@router.get("/config/export")
async def export_config(service: BackupService = Depends(get_backup_service)) -> Response:
    data = await service.export_config()
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="tcms-config.json"'},
    )


@router.post("/config/import", response_model=ImportConfigOut)
async def import_config(
    file: UploadFile = File(...),
    replace: bool = Query(default=True),
    service: BackupService = Depends(get_backup_service),
) -> ImportConfigOut:
    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise ApiError(400, "Файл слишком большой.", "Выберите файл конфигурации меньшего размера.")
    try:
        counts = await service.import_config(data, replace=replace)
    except BackupError as exc:
        raise _fail(exc) from exc
    return ImportConfigOut(
        imported=counts,
        message="Конфигурация импортирована. Перезапустите приложение, если изменения не видны.",
    )
