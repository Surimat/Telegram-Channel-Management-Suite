"""Provider-layer data transfer objects.

Plain dataclasses keep the domain free of any Telegram library types (D-001).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BotIdentity:
    """Minimal identity of a bot as returned by Telegram's ``getMe``."""

    id: int
    username: str
    first_name: str = ""
    can_join_groups: bool | None = None
    can_read_all_group_messages: bool | None = None
    supports_inline_queries: bool | None = None
    can_manage_bots: bool | None = None


@dataclass(slots=True)
class ManagedBotRef:
    """A bot the manager bot can control (from a managed-bot update).

    Represents a Telegram *user* that is a bot. ``user_id`` is the identifier
    used by managed-bot methods (``getManagedBotToken`` and friends).
    """

    user_id: int
    username: str
    first_name: str = ""
    owner_id: int | None = None
    owner_username: str = ""


@dataclass(slots=True)
class ManagedBotAccess:
    """Access settings of a managed bot."""

    is_access_restricted: bool = False
    added_user_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class HealthResult:
    """Outcome of a bot health check."""

    ok: bool
    status: str
    message: str
    how_to_fix: str = ""
    identity: BotIdentity | None = None


@dataclass(slots=True)
class ReactionRecord:
    """A recorded reaction application (used by the fake provider in tests).

    The fake provider never performs I/O; this dataclass lets tests assert which
    bot reacted with which emoji on which message and when.
    """

    chat_id: int | str
    message_id: int
    emoji: str
    applied_at: float
    bot_id: int | None = None
    bot_username: str = ""


# --- MTProto user accounts (PHASE 4) -----------------------------------------


@dataclass(slots=True)
class UserIdentity:
    """Minimal identity of a Telegram *user* account (MTProto ``get_me``).

    Never carries session contents, api_hash or any credential.
    """

    id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    is_premium: bool | None = None
    is_bot: bool = False

    @property
    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username or str(self.id)


@dataclass(slots=True)
class SendCodeResult:
    """Outcome of requesting an authorization code for a phone number."""

    phone_code_hash: str
    code_type: str = ""
    # Which verification step comes next: "code" or "password".
    next_step: str = "code"
    timeout: int | None = None


@dataclass(slots=True)
class SignInResult:
    """Outcome of submitting a code (or 2FA password).

    When ``needs_password`` is True the caller must collect the account's
    two-factor password and call ``sign_in_password``.
    """

    ok: bool
    needs_password: bool = False
    identity: UserIdentity | None = None


@dataclass(slots=True)
class EntityRef:
    """A resolved Telegram entity (channel/group/user) reference."""

    id: int
    username: str = ""
    title: str = ""
    kind: str = ""  # "user" | "group" | "channel"
    participants_count: int | None = None


@dataclass(slots=True)
class SessionFileInfo:
    """Diagnostic information about a Telethon session file (never its content)."""

    exists: bool
    size_bytes: int = 0
    is_readable: bool = False
