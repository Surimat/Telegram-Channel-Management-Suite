"""Google Drive config-sync provider (v1.6).

Moves the encrypted bundle to/from the application's **app-data** folder
(``drive.appdata``) so the app never requests access to the owner's normal Drive
files — the least-privilege scope for a configuration bundle (D-106).

This module is deliberately split so the network/OAuth part is isolated:

* :class:`GoogleDriveConfigSyncProvider` implements the provider protocol over a
  small :class:`DriveTransport` (an OAuth-authorized HTTP client).
* :class:`GoogleDriveOAuth` handles the installed-app OAuth code exchange. It
  needs a client id/secret the owner registers once; there is no bundled secret
  and no VPS — the redirect is the loopback flow Google supports for desktop apps.

If the transport is missing or the token is expired, the provider reports itself
unavailable/needs-reconnect rather than pretending to work. No token is ever
logged or returned.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from backend.app.providers.config_sync_base import ConfigSyncError, RemoteBundle

#: Least-privilege scope: only the app's own hidden data folder.
APPDATA_SCOPE = "https://www.googleapis.com/auth/drive.appdata"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/drive/v3/files"
BUNDLE_NAME = "tcms-config.bundle"


class DriveTransport(Protocol):
    """An authorized HTTP client for Google Drive (injectable for tests)."""

    async def request(
        self, method: str, url: str, *, data: bytes | None = None, params: dict | None = None
    ) -> tuple[int, bytes]:
        ...


@dataclass(slots=True)
class GoogleOAuthConfig:
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://127.0.0.1:8000/api/v1/owner/sync/google/callback"

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


def build_authorization_url(config: GoogleOAuthConfig, state: str) -> str:
    """Return the Google consent URL for the installed-app loopback flow."""
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": APPDATA_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_code(
    config: GoogleOAuthConfig, code: str, *, timeout: float = 20.0
) -> dict[str, object]:
    """Exchange an authorization code for tokens (blocking, loopback flow).

    Returns the parsed token response. Raises :class:`ConfigSyncError` on failure
    without ever including the code or tokens in the message.
    """
    if not config.configured:
        raise ConfigSyncError(
            "Google Drive не настроен.",
            how_to_fix="Укажите client id и client secret Google OAuth.",
        )
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": config.redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_ENDPOINT, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError) as exc:
        raise ConfigSyncError(
            "Не удалось завершить вход в Google.",
            how_to_fix="Проверьте интернет и повторите вход.",
        ) from exc


class GoogleDriveConfigSyncProvider:
    """Store the encrypted bundle in the Drive app-data folder."""

    kind = "google_drive"

    def __init__(self, transport: DriveTransport | None) -> None:
        self.transport = transport

    def available(self) -> bool:
        return self.transport is not None

    async def _find(self) -> str:
        assert self.transport is not None
        status, body = await self.transport.request(
            "GET",
            DRIVE_FILES_ENDPOINT,
            params={"spaces": "appDataFolder", "q": f"name='{BUNDLE_NAME}'", "fields": "files(id)"},
        )
        if status != 200:
            raise ConfigSyncError(
                "Google Drive недоступен.",
                how_to_fix="Переподключите Google Drive.",
            )
        files = json.loads(body or b"{}").get("files", [])
        return files[0]["id"] if files else ""

    async def upload(self, data: bytes, *, revision: int) -> RemoteBundle:
        if self.transport is None:
            raise ConfigSyncError("Google Drive не подключён.")
        file_id = await self._find()
        metadata = {"name": BUNDLE_NAME, "appProperties": {"revision": str(revision)}}
        if file_id:
            url = f"{DRIVE_UPLOAD_ENDPOINT}/{file_id}"
            status, _ = await self.transport.request(
                "PATCH", url, data=data, params={"uploadType": "media"}
            )
        else:
            url = DRIVE_UPLOAD_ENDPOINT
            multipart = _multipart(metadata, data)
            status, _ = await self.transport.request(
                "POST", url, data=multipart, params={"uploadType": "multipart"}
            )
        if status not in (200, 201):
            raise ConfigSyncError(
                "Не удалось выгрузить конфигурацию в Google Drive.",
                how_to_fix="Проверьте подключение и повторите.",
            )
        return RemoteBundle(
            revision=revision, device_id="", device_name="", updated_at="", size=len(data)
        )

    async def download(self) -> tuple[bytes, RemoteBundle] | None:
        if self.transport is None:
            raise ConfigSyncError("Google Drive не подключён.")
        file_id = await self._find()
        if not file_id:
            return None
        status, body = await self.transport.request(
            "GET", f"{DRIVE_FILES_ENDPOINT}/{file_id}", params={"alt": "media"}
        )
        if status != 200:
            raise ConfigSyncError(
                "Не удалось прочитать конфигурацию из Google Drive.",
                how_to_fix="Переподключите Google Drive.",
            )
        return body, RemoteBundle(
            revision=0, device_id="", device_name="", updated_at="", size=len(body),
            reference=file_id,
        )

    async def delete(self) -> None:
        if self.transport is None:
            return
        file_id = await self._find()
        if file_id:
            await self.transport.request("DELETE", f"{DRIVE_FILES_ENDPOINT}/{file_id}")


class GoogleDriveHttpTransport:
    """Minimal authorized HTTP transport for Google Drive.

    Uses the standard library only (``urllib`` in a worker thread), so it adds no
    dependency to the portable build. Only the bearer token is held in memory and
    it is never logged.
    """

    def __init__(self, access_token: str) -> None:
        self._token = access_token

    async def request(
        self, method: str, url: str, *, data: bytes | None = None, params: dict | None = None
    ) -> tuple[int, bytes]:
        import asyncio

        return await asyncio.to_thread(self._request_sync, method, url, data, params)

    def _request_sync(
        self, method: str, url: str, data: bytes | None, params: dict | None
    ) -> tuple[int, bytes]:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/octet-stream",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30.0) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read() if exc.fp else b""
        except urllib.error.URLError as exc:
            raise ConfigSyncError(
                "Google Drive недоступен.",
                how_to_fix="Проверьте интернет и переподключите Google Drive.",
            ) from exc


def _multipart(metadata: dict, data: bytes) -> bytes:
    boundary = "tcms-boundary"
    head = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--".encode()
    return head + data + tail


def write_token_cache(path: Path, tokens: dict[str, object]) -> None:
    """Persist OAuth tokens to a local file (outside git)."""
    path.write_text(json.dumps(tokens), encoding="utf-8")


__all__ = [
    "APPDATA_SCOPE",
    "BUNDLE_NAME",
    "DriveTransport",
    "GoogleDriveConfigSyncProvider",
    "GoogleDriveHttpTransport",
    "GoogleOAuthConfig",
    "build_authorization_url",
    "exchange_code",
    "write_token_cache",
]
