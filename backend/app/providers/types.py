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
    # Access flags observed while resolving the entity (PHASE 5).
    is_admin: bool = False
    # True when Telegram refused to expose the participant list (privacy / not a
    # member / admin-only). The scan then reports NO_ACCESS instead of pretending
    # an empty list means "nobody here".
    participants_hidden: bool = False


@dataclass(slots=True)
class ParticipantPage:
    """One page of participants returned by a streaming scan (PHASE 5).

    ``total`` is Telegram's reported participant count when known; ``exhausted``
    is True when the iterator can yield no more. A page may be empty while the
    scan is not exhausted (e.g. a page of only bots that the caller filtered).
    """

    users: list[UserIdentity] = field(default_factory=list)
    total: int | None = None
    exhausted: bool = False
    # Telegram silently truncates large member lists; the scanner sets this when
    # a page was returned but no further pages are available (partial result).
    truncated: bool = False


@dataclass(slots=True)
class SessionFileInfo:
    """Diagnostic information about a Telethon session file (never its content)."""

    exists: bool
    size_bytes: int = 0
    is_readable: bool = False


# --- Manager bot runtime (post-1.0 hardening) --------------------------------


@dataclass(slots=True)
class BotUpdate:
    """One incoming update received by the manager bot.

    Deliberately minimal: only what the command loop needs. No library types,
    no chat history, no credentials (D-001).
    """

    update_id: int
    kind: str = "message"  # "message" | "other"
    chat_id: int | None = None
    user_id: int | None = None
    username: str = ""
    text: str = ""


# --- Bot ↔ channel administration (product slice: bot-only mode) -------------


@dataclass(slots=True)
class BotChannelStatus:
    """The *verified* status of a bot inside a channel (never assumed).

    ``present`` is only True when Telegram confirmed the bot is a member/admin.
    ``is_admin`` plus the individual ``can_*`` flags come straight from
    ``getChatMember``; a missing flag stays False.
    """

    found: bool = False              # the chat itself resolved
    present: bool = False            # the bot is a member or administrator
    status: str = "unknown"          # administrator | member | left | kicked | unknown
    is_admin: bool = False
    can_post_messages: bool = False
    can_edit_messages: bool = False
    can_delete_messages: bool = False
    can_manage_chat: bool = False
    can_invite_users: bool = False
    can_restrict_members: bool = False
    can_pin_messages: bool = False
    can_set_reactions: bool = False
    chat_id: int | None = None
    chat_title: str = ""
    chat_username: str = ""
    chat_kind: str = ""
    message: str = ""
    how_to_fix: str = ""


@dataclass(slots=True)
class ReactionCapability:
    """The reactions Telegram reports as available in one chat.

    ``available`` is the full emoji set Telegram exposes for the chat;
    ``bot_compatible`` is the subset a bot is allowed to set. Both are honest:
    an empty list with ``determined=False`` means "could not determine", never
    "no reactions exist".
    """

    determined: bool = False
    available: list[str] = field(default_factory=list)
    bot_compatible: list[str] = field(default_factory=list)
    reactions_limit: int = 0
    paid_available: bool = False
    message: str = ""


@dataclass(slots=True)
class InviteLinkResult:
    """A created invite link (safe to display; never a secret)."""

    ok: bool
    link: str = ""
    name: str = ""
    join_request: bool = False
    member_limit: int = 0
    message: str = ""
    how_to_fix: str = ""


@dataclass(slots=True)
class JoinRequestInfo:
    """A join request observed for a chat (Bot API ``ChatJoinRequest``)."""

    user_id: int
    username: str = ""
    display_name: str = ""
    chat_id: int | None = None
    invite_link: str = ""
    created_at: float | None = None


# --- Account permission probe (post-1.0 hardening) ---------------------------


@dataclass(slots=True)
class PermissionReport:
    """Result of probing an account's real access to a channel.

    Every flag states what the Telegram API *actually* confirmed; nothing is
    assumed. ``status`` is one of the machine codes in
    :class:`backend.app.services.permission_service.PermissionStatus`.
    """

    status: str
    channel_found: bool = False
    authorized: bool = False
    can_read_info: bool = False
    can_read_participants: bool = False
    can_invite: bool = False
    session_ok: bool = False

    channel_id: int | None = None
    channel_title: str = ""
    channel_username: str = ""
    channel_kind: str = ""
    participants_count: int | None = None

    message: str = ""
    how_to_fix: str = ""
    retry_after: int | None = None
