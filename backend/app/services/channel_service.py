"""Channel registry service (hardening: one shared channel identity).

Makes a channel a first-class entity so posts, reactions, audience, invites,
permissions and analytics can all refer to the *same* channel instead of asking
the owner to retype it in every section (decision D-051).

Verification reuses the existing read-only permission probe (never bypasses
Telegram limits), and stores only non-secret, display-safe data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import utcnow
from backend.app.db.models.channel import Channel, ChannelKind, ChannelStatus
from backend.app.db.repositories.channels import ChannelRepository
from backend.app.services.events_service import EventsService
from backend.app.services.permission_service import (
    STATUS_ADMIN_REQUIRED,
    STATUS_AUTH_REQUIRED,
    STATUS_ERROR,
    STATUS_FLOOD_WAIT,
    STATUS_NO_ACCESS,
    STATUS_OK,
    STATUS_PARTIAL,
    PermissionService,
    PermissionServiceError,
)
from backend.app.services.session_service import SessionProviderFactory

MODULE = "channels"

# Modules a channel can be connected to. Kept explicit so the UI renders a fixed
# set of toggles and unknown keys are ignored.
KNOWN_MODULES = ("reactions", "audience", "invites", "analytics")

MODULE_LABELS = {
    "reactions": "Реакции",
    "audience": "Аудитория",
    "invites": "Приглашения",
    "analytics": "Аналитика",
}

# Verification statuses that count as usable.
_USABLE_STATUSES = {STATUS_OK, STATUS_PARTIAL}


class ChannelServiceError(Exception):
    """A channel operation failed; carries a friendly message and a hint."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class ChannelVerification:
    """Outcome of verifying a channel against an account."""

    channel_id: str
    status: str  # permission-probe machine status
    status_label: str
    found: bool
    title: str = ""
    username: str = ""
    kind: str = ""
    participants_count: int | None = None
    message: str = ""
    how_to_fix: str = ""
    retry_after: int | None = None


def normalize_reference(reference: str) -> str:
    """Normalize a user-typed channel reference.

    ``https://t.me/name`` and ``t.me/name`` become ``@name``; a bare username
    gets a leading ``@``; numeric ids (e.g. ``-1001234567890``) are kept as-is.
    """
    value = (reference or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    for prefix in ("https://", "http://"):
        if lowered.startswith(prefix):
            value = value[len(prefix):]
            break
    if value.lower().startswith("t.me/"):
        value = value[len("t.me/"):]
    value = value.strip().strip("/")
    if not value:
        return ""
    # Numeric / negative id: keep untouched.
    if value.lstrip("-").isdigit():
        return value
    if not value.startswith("@"):
        value = "@" + value
    return value


class ChannelService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        session_provider_factory: SessionProviderFactory | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = ChannelRepository(session)
        self.events = EventsService(session)
        self._session_provider_factory = session_provider_factory

    # --- inventory -----------------------------------------------------------
    async def list_channels(
        self, *, status: ChannelStatus | None = None, search: str = ""
    ) -> tuple[list[Channel], int]:
        return await self.repo.list(status=status, search=search)

    async def get(self, channel_id: str) -> Channel | None:
        return await self.repo.get(channel_id)

    async def get_default(self) -> Channel | None:
        return await self.repo.get_default()

    async def modules_of(self, channel: Channel) -> dict[str, bool]:
        try:
            raw = json.loads(channel.modules or "{}")
        except (ValueError, TypeError):
            raw = {}
        return {
            name: bool(raw.get(name, False)) if isinstance(raw, dict) else False
            for name in KNOWN_MODULES
        }

    # --- create / update -----------------------------------------------------
    async def add(
        self,
        reference: str,
        *,
        title: str = "",
        kind: ChannelKind = ChannelKind.UNKNOWN,
        make_default: bool = False,
        note: str = "",
    ) -> Channel:
        ref = normalize_reference(reference)
        if not ref:
            raise ChannelServiceError(
                "Укажите канал или группу.",
                how_to_fix="Например: @my_channel, https://t.me/my_channel или ID -100….",
            )
        existing = await self.repo.find_by_reference(ref)
        if existing is not None:
            raise ChannelServiceError(
                "Этот канал уже добавлен.",
                how_to_fix="Откройте его в списке, чтобы проверить или изменить.",
            )
        channel = Channel(
            reference=ref,
            title=title.strip(),
            kind=kind,
            status=ChannelStatus.NEW,
            note=note.strip(),
        )
        await self.repo.add(channel)
        if make_default or await self.repo.count() == 1:
            await self._set_default(channel)
        await self.events.info(
            MODULE,
            f"Канал добавлен: {channel.title or channel.reference}.",
            operation="add_channel",
            status="ok",
        )
        await self.session.commit()
        return channel

    async def update(
        self,
        channel_id: str,
        *,
        title: str | None = None,
        reference: str | None = None,
        note: str | None = None,
        status: ChannelStatus | None = None,
    ) -> Channel:
        channel = await self._require(channel_id)
        if reference is not None:
            ref = normalize_reference(reference)
            if not ref:
                raise ChannelServiceError(
                    "Недопустимая ссылка на канал.",
                    how_to_fix="Укажите @username, ссылку t.me или числовой ID.",
                )
            other = await self.repo.find_by_reference(ref)
            if other is not None and other.id != channel.id:
                raise ChannelServiceError(
                    "Такой канал уже есть в списке.",
                    how_to_fix="Проверьте дубликаты.",
                )
            channel.reference = ref
        if title is not None:
            channel.title = title.strip()
        if note is not None:
            channel.note = note.strip()
        if status is not None:
            channel.status = status
        await self.session.flush()
        await self.session.commit()
        return channel

    async def set_default(self, channel_id: str) -> Channel:
        channel = await self._require(channel_id)
        await self._set_default(channel)
        await self.session.commit()
        return channel

    async def set_modules(self, channel_id: str, modules: dict[str, bool]) -> Channel:
        channel = await self._require(channel_id)
        current = await self.modules_of(channel)
        for name in KNOWN_MODULES:
            if name in modules:
                current[name] = bool(modules[name])
        channel.modules = json.dumps(current)
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Подключение модулей обновлено для {channel.title or channel.reference}.",
            operation="set_modules",
            status="ok",
        )
        await self.session.commit()
        return channel

    async def delete(self, channel_id: str) -> None:
        channel = await self._require(channel_id)
        was_default = channel.is_default
        label = channel.title or channel.reference
        await self.repo.delete(channel)
        if was_default:
            # Promote the next channel so a default always exists when possible.
            remaining, _ = await self.repo.list(limit=1)
            if remaining:
                await self._set_default(remaining[0])
        await self.events.info(
            MODULE,
            f"Канал удалён: {label}.",
            operation="delete_channel",
            status="ok",
        )
        await self.session.commit()

    # --- verification --------------------------------------------------------
    async def verify(self, channel_id: str, account_id: str) -> ChannelVerification:
        """Probe a channel using an account and store the result.

        Read-only: uses the same permission probe as the Sessions page and never
        bypasses Telegram FloodWait / privacy / admin limits.
        """
        channel = await self._require(channel_id)
        probe = PermissionService(
            self.session,
            settings=self.settings,
            session_provider_factory=self._session_provider_factory,
        )
        try:
            result = await probe.check(account_id, channel.reference)
        except PermissionServiceError as exc:
            raise ChannelServiceError(exc.message, how_to_fix=exc.how_to_fix,
                                      status_code=exc.status_code) from exc

        channel.verification_status = result.status
        channel.verification_message = result.message
        channel.verification_hint = result.how_to_fix
        channel.last_verified_at = utcnow()
        if result.target_title:
            channel.title = result.target_title
        if result.channel_username:
            channel.username = result.channel_username.lstrip("@")
        if result.channel_id is not None:
            channel.telegram_id = result.channel_id
        if result.channel_kind:
            channel.kind = _kind_from_str(result.channel_kind)
        if result.participants_count is not None:
            channel.participants_count = result.participants_count

        if result.status in _USABLE_STATUSES:
            channel.status = ChannelStatus.VERIFIED
        elif result.status == STATUS_FLOOD_WAIT:
            channel.status = ChannelStatus.WARNING
        elif result.status in {STATUS_NO_ACCESS, STATUS_ADMIN_REQUIRED,
                              STATUS_AUTH_REQUIRED, STATUS_ERROR}:
            channel.status = ChannelStatus.ERROR
        else:
            channel.status = ChannelStatus.WARNING

        await self.session.flush()
        await self.session.commit()
        return ChannelVerification(
            channel_id=channel.id,
            status=result.status,
            status_label=result.status_label,
            found=result.channel_found,
            title=channel.title,
            username=channel.username,
            kind=channel.kind.value,
            participants_count=channel.participants_count,
            message=result.message,
            how_to_fix=result.how_to_fix,
            retry_after=result.retry_after,
        )

    # --- helpers -------------------------------------------------------------
    async def _require(self, channel_id: str) -> Channel:
        channel = await self.repo.get(channel_id)
        if channel is None:
            raise ChannelServiceError(
                "Канал не найден.",
                how_to_fix="Обновите список каналов.",
                status_code=404,
            )
        return channel

    async def _set_default(self, channel: Channel) -> None:
        await self.repo.clear_default(except_id=channel.id)
        channel.is_default = True
        await self.session.flush()


def _kind_from_str(value: str) -> ChannelKind:
    try:
        return ChannelKind(value)
    except ValueError:
        return ChannelKind.UNKNOWN


__all__ = [
    "KNOWN_MODULES",
    "MODULE_LABELS",
    "ChannelService",
    "ChannelServiceError",
    "ChannelVerification",
    "normalize_reference",
]
