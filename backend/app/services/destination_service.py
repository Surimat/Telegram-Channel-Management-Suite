"""Backup destination service (product slice: pluggable backups).

Manages the list of destinations, their verified status, and delivery of a backup
to every enabled destination. Local delivery is always available; remote
destinations are optional and only contacted when enabled and configured.

Credentials (OAuth tokens) are sealed before storage and never returned by the
API — only an account label and a status are exposed.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import seal_secret
from backend.app.db.base import utcnow
from backend.app.db.models.backup_destination import (
    DESTINATION_TITLES,
    BackupDestination,
    DestinationKind,
    DestinationStatus,
)
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.destinations import DestinationRepository
from backend.app.services.backup_backends import PROVIDER_INFOS, build_backup_provider
from backend.app.services.events_service import EventsService

MODULE = "backup.destinations"


class DestinationServiceError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class DestinationView:
    id: str
    kind: str
    title: str
    label: str
    enabled: bool
    status: str
    account_label: str
    config: dict[str, object]
    last_backup_at: str | None
    last_error: str
    available_space: int | None


@dataclass(slots=True)
class DeliveryResult:
    destination_id: str
    kind: str
    ok: bool
    message: str


class DestinationService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = DestinationRepository(session)
        self.bots = BotRepository(session)
        self.events = EventsService(session)

    # --- inventory -----------------------------------------------------------
    async def list_destinations(self) -> list[DestinationView]:
        rows = await self.repo.list_all()
        return [self._view(row) for row in rows]

    async def ensure_defaults(self) -> list[BackupDestination]:
        """Make sure a local destination always exists."""
        rows = await self.repo.list_all()
        if any(r.kind is DestinationKind.LOCAL for r in rows):
            return rows
        local = BackupDestination(
            kind=DestinationKind.LOCAL,
            label="Локально",
            enabled=True,
            status=DestinationStatus.CONNECTED,
        )
        await self.repo.add(local)
        await self.session.commit()
        rows = await self.repo.list_all()
        return rows

    async def get(self, destination_id: str) -> BackupDestination | None:
        return await self.repo.get(destination_id)

    # --- create / update -----------------------------------------------------
    async def add_destination(
        self,
        kind: DestinationKind,
        *,
        label: str = "",
        enabled: bool = True,
        config: dict[str, object] | None = None,
        token: str = "",
    ) -> BackupDestination:
        existing = await self.repo.find_by_kind(kind)
        if existing is not None:
            raise DestinationServiceError(
                "Такое место хранения уже добавлено.",
                how_to_fix="Измените существующее место хранения.",
            )
        import json

        row = BackupDestination(
            kind=kind,
            label=label.strip() or DESTINATION_TITLES.get(kind, str(kind)),
            enabled=enabled,
            config=json.dumps(config or {}),
            status=DestinationStatus.NOT_CONFIGURED,
        )
        if token:
            row.credentials_encrypted = seal_secret(token.strip(), self.settings)
        await self.repo.add(row)
        await self.session.commit()
        return row

    async def update_destination(
        self,
        destination_id: str,
        *,
        enabled: bool | None = None,
        label: str | None = None,
        config: dict[str, object] | None = None,
        token: str | None = None,
    ) -> BackupDestination:
        import json

        row = await self._require(destination_id)
        if enabled is not None:
            row.enabled = enabled
        if label is not None:
            row.label = label.strip()
        if config is not None:
            row.config = json.dumps(config)
        if token is not None and token.strip():
            row.credentials_encrypted = seal_secret(token.strip(), self.settings)
        await self.session.flush()
        await self.session.commit()
        return row

    async def delete_destination(self, destination_id: str) -> None:
        row = await self._require(destination_id)
        if row.kind is DestinationKind.LOCAL:
            raise DestinationServiceError(
                "Локальное место хранения удалить нельзя.",
                how_to_fix="Его можно только отключить.",
            )
        await self.repo.delete(row)
        await self.session.commit()

    # --- check / deliver -----------------------------------------------------
    async def check(self, destination_id: str) -> DestinationView:
        row = await self._require(destination_id)
        provider = await self._provider_for(row)
        status = provider.check()
        if row.kind is DestinationKind.LOCAL:
            row.status = (
                DestinationStatus.CONNECTED if status.reachable else DestinationStatus.ERROR
            )
        elif not status.configured:
            row.status = DestinationStatus.NOT_CONFIGURED
        elif status.reachable:
            row.status = DestinationStatus.CONNECTED
        else:
            row.status = DestinationStatus.WARNING
        row.account_label = status.account_label
        row.available_space = status.available_space
        row.last_error = "" if status.reachable else status.message
        await self.session.flush()
        await self.session.commit()
        return self._view(row)

    async def deliver(
        self, filename: str, content: bytes, *, caption: str = ""
    ) -> list[DeliveryResult]:
        """Deliver a backup to every enabled destination (best effort)."""
        await self.ensure_defaults()
        results: list[DeliveryResult] = []
        for row in await self.repo.list_all():
            if not row.enabled:
                continue
            provider = await self._provider_for(row)
            result = provider.upload(filename, content, caption=caption)
            if result.ok:
                row.status = DestinationStatus.CONNECTED
                row.last_backup_at = utcnow()
                row.last_error = ""
            else:
                row.status = DestinationStatus.ERROR
                row.last_error = result.message
            results.append(
                DeliveryResult(
                    destination_id=row.id, kind=str(row.kind), ok=result.ok, message=result.message
                )
            )
        await self.session.flush()
        await self.session.commit()
        return results

    # --- helpers -------------------------------------------------------------
    async def _provider_for(self, row: BackupDestination):
        manager = None
        if row.kind is DestinationKind.TELEGRAM:
            manager = await self.bots.get_manager()
        return build_backup_provider(
            row, settings=self.settings, local_dir=self.settings.resolve_backup_dir(),
            manager_bot=manager,
        )

    async def _require(self, destination_id: str) -> BackupDestination:
        row = await self.repo.get(destination_id)
        if row is None:
            raise DestinationServiceError("Место хранения не найдено.", status_code=404)
        return row

    def _view(self, row: BackupDestination) -> DestinationView:
        import json

        try:
            config = json.loads(row.config or "{}")
        except (ValueError, TypeError):
            config = {}
        return DestinationView(
            id=row.id,
            kind=str(row.kind),
            title=DESTINATION_TITLES.get(row.kind, str(row.kind)),
            label=row.label,
            enabled=row.enabled,
            status=str(row.status),
            account_label=row.account_label,
            config=config if isinstance(config, dict) else {},
            last_backup_at=row.last_backup_at.isoformat() if row.last_backup_at else None,
            last_error=row.last_error,
            available_space=row.available_space,
        )


def provider_infos() -> list[dict[str, object]]:
    return [
        {
            "name": info.name,
            "title": info.title,
            "requires_credentials": info.requires_credentials,
            "config_fields": info.config_fields,
            "help": info.help,
        }
        for info in PROVIDER_INFOS
    ]


__all__ = [
    "DeliveryResult",
    "DestinationService",
    "DestinationServiceError",
    "DestinationView",
    "provider_infos",
]
