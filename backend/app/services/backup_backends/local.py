"""Local-disk backup provider (always available).

The default destination: writes the backup into the runtime ``backups`` directory
that the app already manages. It needs no credentials, so the product works fully
with local backups alone.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from backend.app.services.backup_backends.base import (
    ProviderInfo,
    ProviderStatus,
    UploadResult,
)


class LocalBackupProvider:
    name = "local"
    title = "Локально (этот компьютер)"

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def check(self) -> ProviderStatus:
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(self._directory).free
        except OSError as exc:
            return ProviderStatus(
                configured=True,
                reachable=False,
                message=f"Папка резервных копий недоступна: {type(exc).__name__}.",
            )
        return ProviderStatus(
            configured=True,
            reachable=True,
            message="Локальная папка резервных копий доступна.",
            account_label=str(self._directory),
            available_space=int(free),
        )

    def upload(self, filename: str, content: bytes, *, caption: str = "") -> UploadResult:
        target = self._directory / filename
        try:
            target.write_bytes(content)
        except OSError as exc:
            return UploadResult(
                ok=False,
                message=f"Не удалось записать файл: {type(exc).__name__}.",
                how_to_fix="Проверьте права на папку резервных копий и свободное место.",
            )
        return UploadResult(ok=True, message="Копия сохранена локально.", location=str(target))


INFO = ProviderInfo(
    name="local",
    title="Локально (этот компьютер)",
    requires_credentials=False,
    help="Копия сохраняется в папку backups рядом с программой.",
)


__all__ = ["INFO", "LocalBackupProvider"]
