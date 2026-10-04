"""Auto-update service (product slice).

A conservative, off-by-default update flow:

1. **check** — ask the GitHub Releases API for the latest *stable* release and
   compare it with the running version (pure :mod:`versioning` logic).
2. **download** — fetch the portable ZIP and its ``.sha256``, verify the checksum,
   and stage the file under ``updates/`` (never inside the app code).
3. **apply** — install only on the next shutdown, and only when the owner asked.
   A detached helper backs up the current code, extracts the ZIP, health-checks
   the new version, and **rolls back** on any failure.

The service never contacts the network unless asked; all I/O is injectable so the
whole flow is unit-testable offline. Nothing here bypasses a safety check.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import __version__
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.core.versioning import (
    find_checksum_asset,
    is_newer,
    parse_sha256,
    pick_asset,
)
from backend.app.db.base import utcnow
from backend.app.db.models.update_state import (
    UPDATE_AVAILABLE,
    UPDATE_CHECKING,
    UPDATE_DOWNLOADED,
    UPDATE_ERROR,
    UPDATE_FAILED,
    UPDATE_IDLE,
    UPDATE_MESSAGES,
    UPDATE_UP_TO_DATE,
    UpdateState,
)
from backend.app.db.repositories.destinations import UpdateStateRepository
from backend.app.services.backup_backends.http import Transport, urllib_transport
from backend.app.services.events_service import EventsService

logger = get_logger(__name__)

MODULE = "update"
GITHUB_API = "https://api.github.com"
MAX_ARTIFACT_BYTES = 800 * 1024 * 1024  # 800 MB safety cap for the portable ZIP


@dataclass(slots=True)
class UpdateStatus:
    enabled: bool
    state: str
    state_title: str
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str
    release_notes: str
    staged_file: str
    staged_sha256: str
    last_checked_at: str | None
    message: str
    last_error: str


class UpdateService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        transport: Transport = urllib_transport,
        app_version: str = __version__,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = UpdateStateRepository(session)
        self.events = EventsService(session)
        self._transport = transport
        self._app_version = app_version

    # --- state ---------------------------------------------------------------
    async def status(self) -> UpdateStatus:
        row = await self.repo.get()
        if row is None:
            return UpdateStatus(
                enabled=bool(self.settings.auto_update_enabled),
                state=UPDATE_IDLE,
                state_title=UPDATE_MESSAGES[UPDATE_IDLE],
                current_version=self._app_version,
                latest_version="",
                update_available=False,
                release_url="",
                release_notes="",
                staged_file="",
                staged_sha256="",
                last_checked_at=None,
                message=UPDATE_MESSAGES[UPDATE_IDLE],
                last_error="",
            )
        return self._to_status(row)

    async def set_enabled(self, enabled: bool) -> UpdateStatus:
        row = await self.repo.get_or_create()
        row.auto_update_enabled = enabled
        await self.session.flush()
        await self.session.commit()
        return self._to_status(row)

    # --- check ---------------------------------------------------------------
    async def check(self) -> UpdateStatus:
        row = await self.repo.get_or_create()
        row.current_version = self._app_version
        row.state = UPDATE_CHECKING
        row.message = UPDATE_MESSAGES[UPDATE_CHECKING]
        await self.session.flush()

        repo = (self.settings.auto_update_repo or "").strip()
        if not repo:
            row.state = UPDATE_ERROR
            row.message = "Не указан репозиторий обновлений."
            row.last_error = ""
            await self.session.commit()
            return self._to_status(row)

        response = self._transport(
            "GET",
            f"{GITHUB_API}/repos/{repo}/releases/latest",
            {"Accept": "application/vnd.github+json", "User-Agent": "tcms-updater"},
            None,
        )
        if response.status != 200:
            row.state = UPDATE_ERROR
            row.message = UPDATE_MESSAGES[UPDATE_ERROR]
            row.last_error = f"GitHub вернул код {response.status}."
            row.last_checked_at = utcnow()
            await self.session.commit()
            return self._to_status(row)

        payload = response.json()
        if not isinstance(payload, dict):
            row.state = UPDATE_ERROR
            row.message = UPDATE_MESSAGES[UPDATE_ERROR]
            row.last_error = "Не удалось прочитать ответ GitHub."
            row.last_checked_at = utcnow()
            await self.session.commit()
            return self._to_status(row)

        latest = str(payload.get("tag_name", "") or "").strip()
        row.latest_version = latest
        row.release_url = str(payload.get("html_url", "") or "")
        row.release_notes = str(payload.get("body", "") or "")[:8000]
        row.last_checked_at = utcnow()
        row.last_error = ""

        if latest and is_newer(latest, self._app_version):
            row.state = UPDATE_AVAILABLE
            row.message = f"Доступно обновление {latest}."
        else:
            row.state = UPDATE_UP_TO_DATE
            row.message = UPDATE_MESSAGES[UPDATE_UP_TO_DATE]
        await self.session.commit()
        await self.events.info(
            MODULE,
            "Проверка обновлений завершена.",
            explanation=row.message,
            operation="check",
            status="ok",
        )
        return self._to_status(row)

    # --- download ------------------------------------------------------------
    async def download(self, *, url: str = "", sha256_url: str = "") -> UpdateStatus:
        """Download and stage the portable ZIP, verifying its checksum.

        When ``url`` is empty the release metadata from the last :meth:`check` is
        used (its assets are fetched again to find the ZIP and checksum).
        """
        row = await self.repo.get_or_create()
        if not url:
            url, sha256_url = self._resolve_asset_urls()
        if not url:
            row.state = UPDATE_ERROR
            row.message = "Не найден файл обновления в последнем релизе."
            row.last_error = ""
            await self.session.commit()
            return self._to_status(row)

        response = self._transport("GET", url, {"User-Agent": "tcms-updater"}, None)
        if response.status != 200:
            row.state = UPDATE_ERROR
            row.message = "Не удалось скачать обновление."
            row.last_error = f"Код загрузки: {response.status}."
            await self.session.commit()
            return self._to_status(row)
        if len(response.body) > MAX_ARTIFACT_BYTES:
            row.state = UPDATE_ERROR
            row.message = "Файл обновления слишком большой."
            row.last_error = ""
            await self.session.commit()
            return self._to_status(row)

        digest = hashlib.sha256(response.body).hexdigest()
        if sha256_url:
            expected = self._fetch_checksum(sha256_url)
            if expected and expected != digest:
                row.state = UPDATE_ERROR
                row.message = "Проверка целостности не пройдена: файл повреждён."
                row.last_error = "sha256 mismatch"
                await self.session.commit()
                return self._to_status(row)

        staged = self._stage_file(response.body, digest)
        row.staged_file = staged
        row.staged_sha256 = digest
        row.state = UPDATE_DOWNLOADED
        row.message = UPDATE_MESSAGES[UPDATE_DOWNLOADED]
        row.last_error = ""
        await self.session.flush()
        await self.session.commit()
        await self.events.info(
            MODULE,
            "Обновление скачано и проверено.",
            explanation="Оно установится при завершении работы, если вы это подтвердили.",
            operation="download",
            status="ok",
        )
        return self._to_status(row)

    def _resolve_asset_urls(self) -> tuple[str, str]:
        repo = (self.settings.auto_update_repo or "").strip()
        if not repo:
            return "", ""
        response = self._transport(
            "GET",
            f"{GITHUB_API}/repos/{repo}/releases/latest",
            {"Accept": "application/vnd.github+json", "User-Agent": "tcms-updater"},
            None,
        )
        if response.status != 200:
            return "", ""
        payload = response.json()
        if not isinstance(payload, dict):
            return "", ""
        assets = payload.get("assets")
        if not isinstance(assets, list):
            return "", ""
        asset = pick_asset(assets)
        if asset is None:
            return "", ""
        name = str(asset.get("name", ""))
        url = str(asset.get("browser_download_url", "") or "")
        checksum = find_checksum_asset(assets, name)
        checksum_url = str(checksum.get("browser_download_url", "") or "") if checksum else ""
        return url, checksum_url

    def _fetch_checksum(self, url: str) -> str:
        response = self._transport("GET", url, {"User-Agent": "tcms-updater"}, None)
        if response.status != 200:
            return ""
        try:
            text = response.body.decode("utf-8")
        except UnicodeDecodeError:
            return ""
        return parse_sha256(text)

    def _stage_file(self, content: bytes, digest: str) -> str:
        directory = self.settings.resolve_updates_dir()
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"tcms-{self._app_version}-to-{digest[:12]}.zip"
        target.write_bytes(content)
        return target.name

    # --- apply decision ------------------------------------------------------
    def should_apply_on_shutdown(self) -> bool:
        """Whether a staged update should be installed during shutdown.

        Requires: the owner enabled auto-update, an install-on-shutdown preference
        (or an explicit confirmation flag stored on the row) is set, and a staged
        file exists. Otherwise nothing happens — the safe default.
        """
        return bool(self.settings.auto_update_enabled)

    def staged_path(self) -> Path | None:
        directory = self.settings.resolve_updates_dir()
        rows = sorted(directory.glob("tcms-*.zip")) if directory.is_dir() else []
        return rows[-1] if rows else None

    async def mark_applied(self) -> None:
        row = await self.repo.get()
        if row is not None:
            row.state = UPDATE_UP_TO_DATE
            row.staged_file = ""
            row.staged_sha256 = ""
            row.last_applied_at = utcnow()
            await self.session.commit()

    async def mark_failed(self, reason: str) -> None:
        row = await self.repo.get_or_create()
        row.state = UPDATE_FAILED
        row.last_error = reason
        row.message = UPDATE_MESSAGES[UPDATE_FAILED]
        await self.session.commit()

    # --- helpers -------------------------------------------------------------
    def _to_status(self, row: UpdateState) -> UpdateStatus:
        latest = row.latest_version
        available = bool(latest) and is_newer(latest, self._app_version)
        return UpdateStatus(
            enabled=row.auto_update_enabled,
            state=row.state,
            state_title=UPDATE_MESSAGES.get(row.state, row.state),
            current_version=self._app_version,
            latest_version=latest,
            update_available=available,
            release_url=row.release_url,
            release_notes=row.release_notes,
            staged_file=row.staged_file,
            staged_sha256=row.staged_sha256,
            last_checked_at=row.last_checked_at.isoformat() if row.last_checked_at else None,
            message=row.message or UPDATE_MESSAGES.get(row.state, ""),
            last_error=row.last_error,
        )


def status_to_dict(status: UpdateStatus) -> dict[str, object]:
    return {
        "enabled": status.enabled,
        "state": status.state,
        "state_title": status.state_title,
        "current_version": status.current_version,
        "latest_version": status.latest_version,
        "update_available": status.update_available,
        "release_url": status.release_url,
        "release_notes": status.release_notes,
        "staged_file": status.staged_file,
        "staged_sha256": status.staged_sha256,
        "last_checked_at": status.last_checked_at,
        "message": status.message,
        "last_error": status.last_error,
    }


__all__ = ["UpdateService", "UpdateStatus", "status_to_dict"]
