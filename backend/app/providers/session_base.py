"""Abstract MTProto user-account provider (decision D-001, extended in PHASE 4).

Business logic depends only on this interface; Telethon types never leave the
implementation module. Fake implementations let the whole application be tested
without a real account or network access.

The interface is intentionally broader than PHASE 4 needs so that the future
Audience Parser (PHASE 5) and Invite Manager (PHASE 6) can run operations as a
selected account. Only the PHASE 4 subset is implemented today.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.providers.types import (
    EntityRef,
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

    # --- extension points for PHASE 5 / PHASE 6 ------------------------------
    async def resolve_entity(self, username_or_id: str | int) -> EntityRef:
        """Resolve a username/ID to a Telegram entity."""

    async def get_participants(
        self, entity: str | int, *, limit: int = 0
    ) -> list[UserIdentity]:
        """Return participants of a group/channel (subset implemented in PHASE 5)."""

    async def invite_to_channel(self, entity: str | int, user_id: int) -> None:
        """Invite a user to a channel (implemented in PHASE 6)."""
