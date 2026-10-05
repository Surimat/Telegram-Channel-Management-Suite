"""Abstract MTProto user-account provider (decision D-001, extended in PHASE 4).

Business logic depends only on this interface; Telethon types never leave the
implementation module. Fake implementations let the whole application be tested
without a real account or network access.

The interface is intentionally broader than PHASE 4 needs so that the future
Audience Parser (PHASE 5) and Invite Manager (PHASE 6) can run operations as a
selected account. Only the PHASE 4 subset is implemented today.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from backend.app.providers.types import (
    ChannelFetchResult,
    EntityRef,
    ManagedBotRef,
    ParticipantPage,
    PermissionReport,
    SendCodeResult,
    SignInResult,
    UserIdentity,
)


@runtime_checkable
class SessionProvider(Protocol):
    """Operations a Telegram user account must support.

    Implementations MUST NOT log or return session contents, api_hash or any
    other credential, and MUST translate library exceptions into
    :mod:`backend.app.providers.errors`.
    """

    # --- lifecycle (lazy: connect only for the duration of an operation) -----
    async def connect(self) -> None:
        """Open a connection (idempotent). Callers should use ``aclose`` after."""

    async def aclose(self) -> None:
        """Close the connection and release resources (safe to call twice)."""

    # --- identity ------------------------------------------------------------
    async def get_me(self) -> UserIdentity:
        """Return the signed-in account identity (raises if not authorized)."""

    async def health(self) -> UserIdentity:
        """Verify the session is still authorized and reachable."""

    # --- authorization flow --------------------------------------------------
    async def send_code(self, phone: str) -> SendCodeResult:
        """Request a login code for ``phone``. Returns the ``phone_code_hash``."""

    async def sign_in(self, phone: str, code: str, phone_code_hash: str) -> SignInResult:
        """Submit the login code.

        Returns ``needs_password=True`` when the account is protected by 2FA.
        """

    async def sign_in_password(self, password: str) -> SignInResult:
        """Submit the two-factor password and complete sign-in."""

    # --- session file --------------------------------------------------------
    async def export_session(self) -> None:
        """Flush the session to disk (after a successful sign-in)."""

    async def import_string_session(self, value: str, target_path: Path) -> None:
        """Persist a Telethon ``StringSession`` string into ``target_path``.

        The raw string is a secret: implementations MUST NOT log or return it.
        ``target_path`` is a local ``.session`` file inside the sessions directory
        (never a remote resource). Optional: providers that cannot convert may
        raise ``UnsupportedOperationError``.
        """
        ...

    # --- extension points for PHASE 5 / PHASE 6 ------------------------------
    async def resolve_entity(self, username_or_id: str | int) -> EntityRef:
        """Resolve a username/ID to a Telegram entity."""

    async def get_participants(
        self, entity: str | int, *, limit: int = 0
    ) -> list[UserIdentity]:
        """Return participants of a group/channel (subset implemented in PHASE 5)."""

    async def iter_participant_pages(
        self,
        entity: str | int,
        *,
        batch_size: int = 100,
        offset: int = 0,
        limit: int = 0,
    ) -> list[ParticipantPage]:  # pragma: no cover - protocol declaration
        """Fetch participants in pages (streaming scan, PHASE 5).

        Implementations should return one call's worth of pages without holding
        the whole member list in memory. ``offset`` allows a scan to resume from
        where it stopped.
        """
        ...

    async def invite_to_channel(self, entity: str | int, user_id: int) -> None:
        """Invite a user to a channel (implemented in PHASE 6)."""

    async def probe_permissions(self, entity: str | int) -> PermissionReport:
        """Probe this account's *real* access to ``entity`` (post-1.0).

        Must never assume access: each flag is set only when the API confirms it.
        Providers translate library errors into :mod:`backend.app.providers.errors`
        (FloodWait, privacy, admin-required, authorization). Business logic stays
        free of Telethon types (D-001).
        """
        ...

    async def search_public(self, query: str, *, limit: int = 20) -> list[EntityRef]:
        """Search public channels/groups by keyword (donor discovery, v1.1).

        Uses only the official Telegram search the installed library exposes
        (``messages.searchGlobal`` / channel recommendations). Returns whatever
        Telegram actually returns — possibly an empty list — and never bypasses
        limits (D-006). Providers that cannot search raise
        ``UnsupportedOperationError``.
        """
        ...

    async def get_channel_recommendations(
        self, channel: str | int, *, limit: int = 20
    ) -> list[EntityRef]:
        """Return channels Telegram recommends as similar to ``channel`` (v1.1).

        Uses the official ``channels.getChannelRecommendations`` method when the
        installed library exposes it. An empty list means Telegram returned no
        recommendations. Limits are never bypassed.
        """
        ...

    # --- Managed bot factory (v1.3, official MTProto) ------------------------
    async def check_username(self, username: str) -> bool:
        """Return whether ``username`` is available for a managed bot.

        Uses the official ``bots.checkUsername`` method. A False result means
        Telegram reported the username taken/invalid; providers that cannot call
        it raise ``UnsupportedOperationError`` rather than guessing (D-001).
        """
        ...

    async def create_managed_bot(
        self, name: str, username: str, manager_username: str, *, via_deeplink: bool = False
    ) -> ManagedBotRef:
        """Create a managed bot owned by this account, controlled by ``manager_username``.

        Uses the official ``bots.createBot`` method. The manager bot must have
        the ``bot_can_manage_bots`` flag. Telegram enforces its own ownership
        limit (``BOT_CREATE_LIMIT_EXCEEDED``), which is never bypassed (D-006).
        """
        ...

    async def export_managed_bot_token(
        self, bot_username: str, *, revoke: bool = False
    ) -> str:
        """Export a managed bot's token via the manager bot (``bots.exportBotToken``).

        The returned token is a secret: providers MUST NOT log or return it
        anywhere except to the caller, which seals it at rest.
        """
        ...

    async def fetch_channel_messages(
        self, channel: str | int, *, limit: int = 20, min_id: int = 0
    ) -> ChannelFetchResult:
        """Read recent messages from a Telegram channel (content grabber, v1.2).

        ``min_id`` returns only messages newer than that id, so grabbing is
        incremental. Content protection is respected: when the channel forbids
        forwarding/downloading the result sets ``protected=True`` and carries
        only the link — callers must never bypass it (D-006).
        """
        ...

    # --- user-account posting (v1.2: expanded mode only) ---------------------
    async def send_channel_post(
        self,
        channel: str | int,
        *,
        text: str,
        media_paths: list[str] | None = None,
        buttons: list[list[dict[str, object]]] | None = None,
    ) -> ChannelFetchResult:
        """Publish a post as the user account (only where truly needed, v1.2).

        Optional: providers that cannot post raise ``UnsupportedOperationError``.
        Used only in the expanded (session) mode — bot posting is the default.
        """
        ...

    async def delete_channel_messages(
        self, channel: str | int, message_ids: list[int]
    ) -> bool:
        """Delete messages this suite published as the user account (v1.2)."""
        ...
