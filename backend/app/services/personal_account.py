"""Personal Telegram (MTProto) account safety policy.

A personal account can read and act *as the owner*. To make an accidental or
unattended action impossible, every operation that would use a personal session
goes through this policy before a provider is built:

* the **master switch** ``personal_account_enabled`` (default OFF) blocks *all*
  personal-account work — the API, the scheduler and background tasks alike,
  because every MTProto provider is built through a single chokepoint;
* the **mass-action switch** ``invites_enabled`` (default OFF) blocks automatic
  bulk invitations on top of the master switch.

The policy only *refuses*: it never evades a Telegram restriction and never
retries a dangerous action (D-006). Operations that use the Telegram **Bot API**
never consult this policy, so ordinary bot work keeps working while the personal
account is switched off.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.services.settings_service import SettingsService

MODULE = "personal_account"

#: UI-editable personal-account switches: key → (title, type, default attr).
PERSONAL_ACCOUNT_SETTING_SPECS: dict[str, tuple[str, str, str]] = {
    "personal_account_enabled": (
        "Личный аккаунт (MTProto)",
        "bool",
        "personal_account_enabled",
    ),
    "invites_enabled": (
        "Автоматические приглашения",
        "bool",
        "invites_enabled",
    ),
}

_DISABLED_MESSAGE = (
    "Операции через личный Telegram-аккаунт выключены на сервере. "
    "Обычные действия через бота продолжают работать."
)
_DISABLED_HINT = (
    "Включите «Личный аккаунт (MTProto)» в разделе «Настройки». Держите его "
    "выключенным, пока личный аккаунт действительно не нужен."
)
_INVITES_MESSAGE = "Автоматические приглашения выключены на сервере."
_INVITES_HINT = (
    "Включите «Автоматические приглашения» в разделе «Настройки», чтобы "
    "подготовить и подтвердить массовое приглашение."
)


class PersonalAccountDisabledError(Exception):
    """A personal-account operation was blocked by the server policy.

    Carries a friendly ``message`` and an actionable ``how_to_fix`` so the API can
    answer "what happened?" and "how do I fix it?" (D-016). It is mapped to HTTP
    403 by the API error handler.
    """

    def __init__(
        self,
        message: str = _DISABLED_MESSAGE,
        *,
        how_to_fix: str = _DISABLED_HINT,
        status_code: int = 403,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


def _as_bool(value: object) -> bool:
    """Coerce a stored setting value to a bool.

    The generic settings API stores values as strings, so a switch written there
    may carry ``"true"``/``"false"``; reading it through ``get_typed`` returns the
    raw string for a string-typed row. Treat anything that is not an explicit
    truthy token as ``False`` so an unset or mistyped switch can never be read as
    enabled.
    """
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


class PersonalAccountPolicy:
    """Read the personal-account switches and refuse unsafe operations."""

    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def _flag(self, key: str) -> bool:
        spec = PERSONAL_ACCOUNT_SETTING_SPECS[key]
        default = bool(getattr(self.settings, spec[2]))
        value = await SettingsService(self.session).get_typed(key, default)
        return _as_bool(value)

    async def personal_account_enabled(self) -> bool:
        """True when operations through a personal account are allowed."""
        return await self._flag("personal_account_enabled")

    async def invites_enabled(self) -> bool:
        """True when automatic (bulk) invitations are allowed."""
        return await self._flag("invites_enabled")

    async def status(self) -> dict[str, bool]:
        """Return the current switches without raising (for status/summary)."""
        return {
            "personal_account_enabled": await self.personal_account_enabled(),
            "invites_enabled": await self.invites_enabled(),
        }

    async def require_enabled(self) -> None:
        """Refuse any personal-account (MTProto) operation unless explicitly on."""
        if not await self.personal_account_enabled():
            raise PersonalAccountDisabledError()

    async def require_invites_enabled(self) -> None:
        """Refuse automatic invitations unless both switches are on."""
        await self.require_enabled()
        if not await self.invites_enabled():
            raise PersonalAccountDisabledError(_INVITES_MESSAGE, how_to_fix=_INVITES_HINT)

    async def invites_allowed(self) -> bool:
        """True only when both the master and the invites switches are on."""
        return await self.personal_account_enabled() and await self.invites_enabled()


async def ensure_personal_account_settings(session: AsyncSession) -> None:
    """Create the personal-account switches with their safe defaults (idempotent).

    Only a *missing* row is created; an existing owner choice is never
    overwritten. Seeding the rows gives them a real ``bool`` type so the settings
    API and the UI show them as switches rather than free text.
    """
    from backend.app.db.repositories.settings import SettingRepository

    settings = get_settings()
    repo = SettingRepository(session)
    for key, (title, _type, attr) in PERSONAL_ACCOUNT_SETTING_SPECS.items():
        if await repo.get(key) is not None:
            continue
        default = bool(getattr(settings, attr))
        await repo.upsert(
            key,
            "true" if default else "false",
            value_type="bool",
            title=title,
            default_value="true" if default else "false",
        )


__all__ = [
    "MODULE",
    "PERSONAL_ACCOUNT_SETTING_SPECS",
    "PersonalAccountDisabledError",
    "PersonalAccountPolicy",
    "ensure_personal_account_settings",
]
