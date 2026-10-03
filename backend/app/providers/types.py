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
