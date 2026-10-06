"""Local-folder config-sync provider (v1.6).

Stores the encrypted bundle in a directory the owner chooses (default: a
``sync/`` folder next to the app data). It is the offline, zero-account option —
useful on one PC or with a folder the owner already syncs themselves. It handles
ciphertext only.
"""

from __future__ import annotations

from pathlib import Path

from backend.app.providers.config_sync_base import ConfigSyncError, RemoteBundle

BUNDLE_FILENAME = "tcms-config.bundle"


class LocalConfigSyncProvider:
    """Write/read the encrypted bundle in a local directory."""

    kind = "local"

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def _path(self) -> Path:
        return self.directory / BUNDLE_FILENAME

    def available(self) -> bool:
        return bool(str(self.directory))

    async def upload(self, data: bytes, *, revision: int) -> RemoteBundle:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._path().write_bytes(data)
        except OSError as exc:
            raise ConfigSyncError(
                "Не удалось записать файл конфигурации.",
                how_to_fix="Проверьте права на папку синхронизации.",
            ) from exc
        return RemoteBundle(
            revision=revision,
            device_id="",
            device_name="",
            updated_at="",
            size=len(data),
            reference=str(self._path()),
        )

    async def download(self) -> tuple[bytes, RemoteBundle] | None:
        path = self._path()
        if not path.is_file():
            return None
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ConfigSyncError(
                "Не удалось прочитать файл конфигурации.",
                how_to_fix="Проверьте доступ к папке синхронизации.",
            ) from exc
        return data, RemoteBundle(
            revision=0, device_id="", device_name="", updated_at="",
            size=len(data), reference=str(path),
        )

    async def delete(self) -> None:
        path = self._path()
        if path.is_file():
            path.unlink()


__all__ = ["BUNDLE_FILENAME", "LocalConfigSyncProvider"]
