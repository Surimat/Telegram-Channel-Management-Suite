"""Yandex Disk backup provider (optional).

Uploads a backup to Yandex Disk via its REST API using an OAuth token. The token
is passed in from the sealed destination credentials; it is never logged or
returned. Network access happens only when the owner enabled this destination.

Flow: ``GET /v1/disk/resources/upload?path=...&overwrite=true`` → upload URL →
``PUT`` the bytes. A ``Transport`` can be injected for tests.
"""

from __future__ import annotations

from backend.app.services.backup_backends.base import (
    ProviderInfo,
    ProviderStatus,
    UploadResult,
)
from backend.app.services.backup_backends.http import Transport, request_json, urllib_transport

API_BASE = "https://cloud-api.yandex.net/v1/disk"


class YandexDiskBackupProvider:
    name = "yandex_disk"
    title = "Яндекс Диск"

    def __init__(
        self,
        *,
        token: str = "",
        folder: str = "tcms-backups",
        transport: Transport = urllib_transport,
    ) -> None:
        self._token = token or ""
        self._folder = (folder or "tcms-backups").strip("/")
        self._transport = transport

    def check(self) -> ProviderStatus:
        if not self._token:
            return ProviderStatus(
                configured=False,
                reachable=False,
                message="Не подключено: нужен OAuth-токен Яндекс Диска.",
            )
        response, _ = request_json(
            self._transport,
            "GET",
            f"{API_BASE}/?fields=total_space,used_space",
            token=self._token,
        )
        if response.status != 200:
            return ProviderStatus(
                configured=True,
                reachable=False,
                message="Не удалось подключиться к Яндекс Диску. Проверьте токен.",
            )
        return ProviderStatus(
            configured=True,
            reachable=True,
            message="Яндекс Диск доступен.",
            account_label=self._folder,
        )

    def upload(self, filename: str, content: bytes, *, caption: str = "") -> UploadResult:
        if not self._token:
            return UploadResult(
                ok=False,
                message="Не подключено: нужен OAuth-токен Яндекс Диска.",
                how_to_fix="Подключите Яндекс Диск в настройках резервных копий.",
            )
        remote_path = f"{self._folder}/{filename}"
        response, payload = request_json(
            self._transport,
            "GET",
            f"{API_BASE}/resources/upload?path={remote_path}&overwrite=true",
            token=self._token,
        )
        if response.status != 200 or not isinstance(payload, dict):
            return UploadResult(
                ok=False,
                message="Яндекс Диск отклонил запрос на загрузку.",
                how_to_fix="Проверьте токен и свободное место.",
            )
        href = str(payload.get("href", ""))
        if not href:
            return UploadResult(ok=False, message="Яндекс Диск не вернул ссылку для загрузки.")
        upload_response = self._transport("PUT", href, {}, content)
        if upload_response.status not in (200, 201, 202):
            return UploadResult(
                ok=False,
                message="Не удалось загрузить файл на Яндекс Диск.",
                how_to_fix="Повторите попытку позже.",
            )
        return UploadResult(
            ok=True, message="Копия отправлена на Яндекс Диск.", location=remote_path
        )


INFO = ProviderInfo(
    name="yandex_disk",
    title="Яндекс Диск",
    requires_credentials=True,
    config_fields=["folder"],
    help="Нужен OAuth-токен Яндекс Диска. Токен хранится в зашифрованном виде.",
)


__all__ = ["INFO", "YandexDiskBackupProvider"]
