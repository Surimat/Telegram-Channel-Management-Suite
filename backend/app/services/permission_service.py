"""Account permission probe service (post-1.0 hardening).

Answers "can this account actually work with this channel?" using the existing
:class:`SessionProvider` abstraction. It never assumes access: the provider
reports only what Telegram confirms, and this service turns that into a stable
machine status plus plain-language guidance for the UI.

This is intentionally separate from :class:`InviteService` — a probe is a
read-only diagnostic, not part of a bulk operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import utcnow
from backend.app.db.models.permission import PermissionCheck
from backend.app.db.repositories.permissions import PermissionCheckRepository
from backend.app.providers.errors import (
    ChatAdminRequiredError,
    EntityNotFoundError,
    FloodWaitError,
    NetworkError,
    PrivacyRestrictedError,
    SessionInvalidError,
    TelegramProviderError,
)
from backend.app.providers.types import PermissionReport
from backend.app.services.events_service import EventsService
from backend.app.services.session_service import SessionProviderFactory, SessionService

MODULE = "permissions"

# Machine statuses (mirrored by the frontend and docs/API.md).
STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_NO_ACCESS = "no_access"
STATUS_AUTH_REQUIRED = "auth_required"
STATUS_ADMIN_REQUIRED = "admin_required"
STATUS_PRIVACY_RESTRICTED = "privacy_restricted"
STATUS_FLOOD_WAIT = "flood_wait"
STATUS_ERROR = "error"

STATUS_LABELS = {
    STATUS_OK: "Всё доступно",
    STATUS_PARTIAL: "Частичный доступ",
    STATUS_NO_ACCESS: "Нет доступа",
    STATUS_AUTH_REQUIRED: "Требуется авторизация",
    STATUS_ADMIN_REQUIRED: "Нужны права администратора",
    STATUS_PRIVACY_RESTRICTED: "Данные скрыты Telegram",
    STATUS_FLOOD_WAIT: "Telegram просит подождать",
    STATUS_ERROR: "Ошибка проверки",
}


class PermissionServiceError(Exception):
    """A friendly, user-facing permission-probe error."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class PermissionResult:
    """Outcome of one permission probe, ready for the API/UI."""

    status: str
    status_label: str
    account_id: str
    account_label: str
    target: str
    target_title: str = ""
    channel_found: bool = False
    authorized: bool = False
    can_read_info: bool = False
    can_read_participants: bool = False
    can_invite: bool = False
    session_ok: bool = False
    channel_id: int | None = None
    channel_username: str = ""
    channel_kind: str = ""
    participants_count: int | None = None
    message: str = ""
    how_to_fix: str = ""
    retry_after: int | None = None
    checked_at: Any = None
    check_id: str | None = None


class PermissionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        session_provider_factory: SessionProviderFactory | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = PermissionCheckRepository(session)
        self.events = EventsService(session)
        self._session_provider_factory = session_provider_factory

    def _session_service(self) -> SessionService:
        kwargs: dict[str, Any] = {"settings": self.settings}
        if self._session_provider_factory is not None:
            kwargs["provider_factory"] = self._session_provider_factory
        return SessionService(self.session, **kwargs)

    async def check(self, account_id: str, target: str) -> PermissionResult:
        """Probe ``account_id`` access to ``target`` and persist the result."""
        target = (target or "").strip()
        if not target:
            raise PermissionServiceError(
                "Укажите канал, группу или пользователя.",
                how_to_fix="Например: @channel, https://t.me/channel или ID.",
            )
        service = self._session_service()
        account = await service.get(account_id)
        if account is None:
            raise PermissionServiceError(
                "Аккаунт не найден.",
                how_to_fix="Обновите список аккаунтов и выберите доступный.",
                status_code=404,
            )
        account_label = (
            account.display_name or account.username or account.phone_masked or account.id
        )

        provider = service.provider_for(account)
        try:
            report = await provider.probe_permissions(target)
        except TelegramProviderError as exc:
            result = self._from_error(exc, account_id, account_label, target)
        except Exception as exc:  # pragma: no cover - defensive
            result = PermissionResult(
                status=STATUS_ERROR,
                status_label=STATUS_LABELS[STATUS_ERROR],
                account_id=account_id,
                account_label=account_label,
                target=target,
                message="Не удалось выполнить проверку.",
                how_to_fix="Повторите попытку позже.",
            )
            await self.events.error(
                MODULE,
                f"Проверка доступа не удалась для {account_label}.",
                explanation="Непредвиденная ошибка.",
                operation="permission_probe",
                status="error",
                details=type(exc).__name__,
            )
        else:
            result = self._from_report(report, account_id, account_label, target)
        finally:
            await provider.aclose()

        check = await self._persist(result)
        result.check_id = check.id
        result.checked_at = check.created_at
        await self.events.info(
            MODULE,
            f"Проверка доступа: {account_label} → {result.target_title or target}.",
            explanation=result.message,
            how_to_fix=result.how_to_fix,
            actor=account_label,
            operation="permission_probe",
            status=result.status,
        )
        await self.session.commit()
        return result

    # --- mapping helpers -----------------------------------------------------
    def _from_report(
        self, report: PermissionReport, account_id: str, account_label: str, target: str
    ) -> PermissionResult:
        status = report.status if report.status in STATUS_LABELS else STATUS_ERROR
        return PermissionResult(
            status=status,
            status_label=STATUS_LABELS[status],
            account_id=account_id,
            account_label=account_label,
            target=target,
            target_title=report.channel_title or target,
            channel_found=report.channel_found,
            authorized=report.authorized,
            can_read_info=report.can_read_info,
            can_read_participants=report.can_read_participants,
            can_invite=report.can_invite,
            session_ok=report.session_ok,
            channel_id=report.channel_id,
            channel_username=report.channel_username,
            channel_kind=report.channel_kind,
            participants_count=report.participants_count,
            message=report.message,
            how_to_fix=report.how_to_fix,
            retry_after=report.retry_after,
        )

    def _from_error(
        self, exc: TelegramProviderError, account_id: str, account_label: str, target: str
    ) -> PermissionResult:
        if isinstance(exc, FloodWaitError):
            status = STATUS_FLOOD_WAIT
        elif isinstance(exc, SessionInvalidError):
            status = STATUS_AUTH_REQUIRED
        elif isinstance(exc, ChatAdminRequiredError):
            status = STATUS_ADMIN_REQUIRED
        elif isinstance(exc, PrivacyRestrictedError):
            status = STATUS_PRIVACY_RESTRICTED
        elif isinstance(exc, EntityNotFoundError):
            status = STATUS_NO_ACCESS
        elif isinstance(exc, NetworkError):
            status = STATUS_ERROR
        else:
            status = STATUS_ERROR
        return PermissionResult(
            status=status,
            status_label=STATUS_LABELS[status],
            account_id=account_id,
            account_label=account_label,
            target=target,
            target_title=target,
            message=exc.message,
            how_to_fix=exc.how_to_fix,
            retry_after=exc.retry_after,
        )

    async def _persist(self, result: PermissionResult) -> PermissionCheck:
        check = PermissionCheck(
            account_id=result.account_id,
            account_label=result.account_label,
            target=result.target,
            target_title=result.target_title,
            status=result.status,
            channel_found=result.channel_found,
            authorized=result.authorized,
            can_read_info=result.can_read_info,
            can_read_participants=result.can_read_participants,
            can_invite=result.can_invite,
            session_ok=result.session_ok,
            channel_id=result.channel_id,
            participants_count=result.participants_count,
            message=result.message,
            how_to_fix=result.how_to_fix,
            checked_at=utcnow(),
        )
        return await self.repo.add(check)

    async def latest(self) -> PermissionResult | None:
        check = await self.repo.latest()
        return self._to_result(check) if check else None

    async def history(self, limit: int = 20) -> list[PermissionResult]:
        checks = await self.repo.list_recent(limit=limit)
        return [self._to_result(c) for c in checks]

    def _to_result(self, check: PermissionCheck) -> PermissionResult:
        return PermissionResult(
            status=check.status,
            status_label=STATUS_LABELS.get(check.status, check.status),
            account_id=check.account_id,
            account_label=check.account_label,
            target=check.target,
            target_title=check.target_title,
            channel_found=check.channel_found,
            authorized=check.authorized,
            can_read_info=check.can_read_info,
            can_read_participants=check.can_read_participants,
            can_invite=check.can_invite,
            session_ok=check.session_ok,
            channel_id=check.channel_id,
            participants_count=check.participants_count,
            message=check.message,
            how_to_fix=check.how_to_fix,
            checked_at=check.created_at,
            check_id=check.id,
        )


__all__ = [
    "MODULE",
    "STATUS_ADMIN_REQUIRED",
    "STATUS_AUTH_REQUIRED",
    "STATUS_ERROR",
    "STATUS_FLOOD_WAIT",
    "STATUS_LABELS",
    "STATUS_NO_ACCESS",
    "STATUS_OK",
    "STATUS_PARTIAL",
    "STATUS_PRIVACY_RESTRICTED",
    "PermissionResult",
    "PermissionService",
    "PermissionServiceError",
]
