"""Google Drive backup provider (optional).

Uploads a backup to Google Drive using an OAuth access token. The token is passed
in from the sealed destination credentials; it is never logged or returned.
Network access happens only when the owner enabled this destination.

Flow: a resumable upload session (``POST .../files?uploadType=resumable``) then a
single ``PUT`` of the bytes. A ``Transport`` can be injected for tests.
"""

from __future__ import annotations

import json

from backend.app.services.backup_backends.base import (
    ProviderInfo,
    ProviderStatus,
    UploadResult,
)
from backend.app.services.backup_backends.http import Transport, urllib_transport

API_BASE = "https://www.googleapis.com/drive/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"


class GoogleDriveBackupProvider:
    name = "google_drive"
    title = "Google Drive"

    def __init__(
        self,
        *,
        token: str = "",
        folder_id: str = "",
        transport: Transport = urllib_transport,
    ) -> None:
        self._token = token or ""
        self._folder_id = folder_id or ""
        self._transport = transport

    def check(self) -> ProviderStatus:
        if not self._token:
            return ProviderStatus(
                configured=False,
                reachable=False,
                message="Не подключено: нужен токен Google Drive.",
            )
        response = self._transport(
            "GET",
            f"{API_BASE}/about?fields=user",
            {"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
            None,
        )
        if response.status != 200:
            return ProviderStatus(
                configured=True,
                reachable=False,
                message="Не удалось подключиться к Google Drive. Проверьте токен.",
            )
        label = ""
        payload = response.json()
        if isinstance(payload, dict):
            label = str((payload.get("user") or {}).get("emailAddress", ""))
        return ProviderStatus(
            configured=True,
            reachable=True,
            message="Google Drive доступен.",
            account_label=label or self._folder_id,
        )

    def upload(self, filename: str, content: bytes, *, caption: str = "") -> UploadResult:
        if not self._token:
            return UploadResult(
                ok=False,
                message="Не подключено: нужен токен Google Drive.",
                how_to_fix="Подключите Google Drive в настройках резервных копий.",
            )
        metadata: dict[str, object] = {"name": filename}
        if self._folder_id:
            metadata["parents"] = [self._folder_id]
        init_headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "application/octet-stream",
        }
        init = self._transport(
            "POST",
            f"{UPLOAD_BASE}/files?uploadType=resumable",
            init_headers,
            json.dumps(metadata).encode("utf-8"),
        )
        if init.status not in (200, 201):
            return UploadResult(
                ok=False,
                message="Google Drive отклонил запрос на загрузку.",
                how_to_fix="Проверьте токен и папку.",
            )
        upload_url = init.headers.get("location", "")
        if not upload_url:
            return UploadResult(ok=False, message="Google Drive не вернул ссылку для загрузки.")
        upload = self._transport(
            "PUT",
            upload_url,
            {"Content-Type": "application/octet-stream"},
            content,
        )
        if upload.status not in (200, 201):
            return UploadResult(
                ok=False,
                message="Не удалось загрузить файл в Google Drive.",
                how_to_fix="Повторите попытку позже.",
            )
        return UploadResult(ok=True, message="Копия отправлена в Google Drive.", location=filename)


INFO = ProviderInfo(
    name="google_drive",
    title="Google Drive",
    requires_credentials=True,
    config_fields=["folder_id"],
    help="Нужен токен доступа Google Drive. Токен хранится в зашифрованном виде.",
)


__all__ = ["INFO", "GoogleDriveBackupProvider"]
