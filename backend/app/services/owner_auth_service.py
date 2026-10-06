"""Owner Auth service (v1.6).

A local, offline identity that protects the Suite. It is independent of any
Telegram account or session (D-105). Responsibilities:

* create the owner profile (password or PIN) with a PBKDF2 verifier;
* log in / log out and lock / unlock;
* rate-limit repeated wrong attempts;
* decide whether a request may proceed (used by the API guard);
* derive the config-bundle key at unlock time (never stored).

Passwords and PINs are never stored, logged or returned. The service never emits
the secret in an error message.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core import i18n
from backend.app.core.owner_security import (
    OwnerSecretError,
    derive_bundle_key,
    generate_salt,
    hash_secret,
    verify_secret,
)
from backend.app.db.base import utcnow
from backend.app.db.models.owner import METHOD_TITLES, OwnerAuthMethod, OwnerIdentity
from backend.app.db.repositories.owners import OwnerRepository
from backend.app.services.events_service import EventsService

MODULE = "owner"

MIN_SECRET_LENGTH = 4
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15


class OwnerAuthError(Exception):
    """A friendly, secret-free error for the owner-auth API."""

    def __init__(self, message: str, *, status_code: int = 400, how_to_fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.how_to_fix = how_to_fix


@dataclass(slots=True)
class OwnerStatus:
    exists: bool
    enabled: bool
    locked: bool
    method: str
    method_title: str
    display_name: str
    last_login_at: str
    failed_attempts: int
    locked_until: str
    recovery_hint: str
    #: True when the app is protected and the caller is not authenticated.
    auth_required: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "exists": self.exists,
            "enabled": self.enabled,
            "locked": self.locked,
            "method": self.method,
            "method_title": self.method_title,
            "display_name": self.display_name,
            "last_login_at": self.last_login_at,
            "failed_attempts": self.failed_attempts,
            "locked_until": self.locked_until,
            "recovery_hint": self.recovery_hint,
            "auth_required": self.auth_required,
        }


class OwnerAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = OwnerRepository(session)
        self.events = EventsService(session)

    # --- reads ---------------------------------------------------------------
    async def get_identity(self) -> OwnerIdentity | None:
        return await self.repo.get_single()

    async def exists(self) -> bool:
        return await self.repo.get_single() is not None

    async def is_enabled(self) -> bool:
        owner = await self.repo.get_single()
        return bool(owner and owner.enabled)

    async def status(self) -> OwnerStatus:
        owner = await self.repo.get_single()
        if owner is None:
            return OwnerStatus(
                exists=False,
                enabled=False,
                locked=False,
                method="",
                method_title="",
                display_name="",
                last_login_at="",
                failed_attempts=0,
                locked_until="",
                recovery_hint="",
                auth_required=False,
            )
        return OwnerStatus(
            exists=True,
            enabled=owner.enabled,
            locked=bool(owner.locked_until and _aware(owner.locked_until) > utcnow()),
            method=owner.method.value,
            method_title=METHOD_TITLES.get(owner.method, owner.method.value),
            display_name=owner.display_name,
            last_login_at=owner.last_login_at.isoformat() if owner.last_login_at else "",
            failed_attempts=owner.failed_attempts,
            locked_until=owner.locked_until.isoformat() if owner.locked_until else "",
            recovery_hint=owner.recovery_hint,
            auth_required=owner.enabled,
        )

    # --- lifecycle -----------------------------------------------------------
    async def create(
        self,
        secret: str,
        *,
        method: OwnerAuthMethod | str = OwnerAuthMethod.PASSWORD,
        display_name: str = "",
        recovery_hint: str = "",
    ) -> OwnerIdentity:
        if await self.repo.get_single() is not None:
            raise OwnerAuthError(
                i18n.translate("owner.already_exists"),
                status_code=409,
                how_to_fix="Используйте вход или удалите профиль владельца.",
            )
        self._validate_secret(secret)
        method_enum = self._coerce_method(method)
        owner = OwnerIdentity(
            display_name=display_name.strip(),
            method=method_enum,
            verifier=hash_secret(secret),
            sync_salt=generate_salt(),
            enabled=True,
            recovery_hint=recovery_hint.strip()[:200],
        )
        await self.repo.add(owner)
        await self.events.info(MODULE, "Профиль владельца создан.", operation="create")
        await self.session.commit()
        return owner

    async def login(self, secret: str) -> OwnerIdentity:
        owner = await self.repo.get_single()
        if owner is None:
            raise OwnerAuthError(
                i18n.translate("owner.no_profile"),
                status_code=404,
                how_to_fix="Создайте профиль владельца.",
            )
        if owner.locked_until and _aware(owner.locked_until) > utcnow():
            raise OwnerAuthError(
                i18n.translate("owner.locked"),
                status_code=423,
                how_to_fix="Подождите или перезапустите приложение, чтобы снять блокировку.",
            )
        if not verify_secret(secret, owner.verifier):
            await self._register_failure(owner)
            raise OwnerAuthError(i18n.translate("owner.bad_password"), status_code=401)

        owner.failed_attempts = 0
        owner.locked_until = None
        owner.last_login_at = utcnow()
        await self.session.commit()
        return owner

    async def logout(self) -> None:
        await self.events.info(MODULE, "Владелец вышел.", operation="logout")
        await self.session.commit()

    async def lock(self) -> OwnerStatus:
        owner = await self.repo.get_single()
        if owner is None:
            raise OwnerAuthError(i18n.translate("owner.no_profile"), status_code=404)
        owner.enabled = True
        await self.session.commit()
        await self.events.info(MODULE, "Приложение заблокировано.", operation="lock")
        return await self.status()

    async def unlock(self, secret: str) -> OwnerIdentity:
        return await self.login(secret)

    async def set_enabled(self, enabled: bool) -> OwnerStatus:
        owner = await self.repo.get_single()
        if owner is None:
            raise OwnerAuthError(i18n.translate("owner.no_profile"), status_code=404)
        owner.enabled = enabled
        if not enabled:
            owner.failed_attempts = 0
            owner.locked_until = None
        await self.session.commit()
        await self.events.info(
            MODULE,
            "Защита приложения включена." if enabled else "Защита приложения выключена.",
            operation="set_enabled",
        )
        return await self.status()

    async def change_secret(self, current: str, new_secret: str) -> None:
        owner = await self.repo.get_single()
        if owner is None:
            raise OwnerAuthError(i18n.translate("owner.no_profile"), status_code=404)
        if not verify_secret(current, owner.verifier):
            raise OwnerAuthError(i18n.translate("owner.bad_password"), status_code=401)
        self._validate_secret(new_secret)
        owner.verifier = hash_secret(new_secret)
        await self.session.commit()
        await self.events.info(MODULE, "Пароль владельца изменён.", operation="change_secret")

    async def delete(self) -> None:
        owner = await self.repo.get_single()
        if owner is not None:
            await self.repo.delete(owner)
            await self.session.commit()
            await self.events.info(MODULE, "Профиль владельца удалён.", operation="delete")

    # --- config-bundle key (never stored) ------------------------------------
    async def derive_key(self, secret: str) -> bytes:
        owner = await self.repo.get_single()
        if owner is None or not verify_secret(secret, owner.verifier):
            raise OwnerAuthError(i18n.translate("owner.bad_password"), status_code=401)
        return derive_bundle_key(secret, owner.sync_salt)

    # --- helpers -------------------------------------------------------------
    @staticmethod
    def _coerce_method(method: OwnerAuthMethod | str) -> OwnerAuthMethod:
        if isinstance(method, OwnerAuthMethod):
            return method
        try:
            return OwnerAuthMethod(str(method).lower())
        except ValueError:
            return OwnerAuthMethod.PASSWORD

    @staticmethod
    def _validate_secret(secret: str) -> None:
        if not secret or len(secret.strip()) < MIN_SECRET_LENGTH:
            raise OwnerAuthError(
                i18n.translate("owner.secret_too_short"),
                status_code=400,
                how_to_fix=f"Используйте не менее {MIN_SECRET_LENGTH} символов.",
            )

    async def _register_failure(self, owner: OwnerIdentity) -> None:
        owner.failed_attempts = (owner.failed_attempts or 0) + 1
        if owner.failed_attempts >= MAX_FAILED_ATTEMPTS:
            owner.locked_until = utcnow() + timedelta(minutes=LOCK_MINUTES)
        await self.session.commit()
        await self.events.warning(MODULE, "Неудачная попытка входа.", operation="login")


def _aware(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime (SQLite drops tzinfo)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def derive_key_or_raise(secret: str, sync_salt: str) -> bytes:
    """Pure helper for callers that already hold the salt (used by tests)."""
    try:
        return derive_bundle_key(secret, sync_salt)
    except OwnerSecretError as exc:  # pragma: no cover - defensive
        raise OwnerAuthError(str(exc), status_code=400) from exc


__all__ = [
    "MAX_FAILED_ATTEMPTS",
    "MIN_SECRET_LENGTH",
    "OwnerAuthError",
    "OwnerAuthService",
    "OwnerStatus",
    "derive_key_or_raise",
]
