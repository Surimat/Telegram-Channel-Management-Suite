"""Deterministic fake MTProto user-account provider.

Used by tests and by the app's offline/dev mode so the whole Session Manager
business logic can run without real credentials or network access. It performs
no network I/O (it may create a small placeholder session file to simulate the
side effect of a completed sign-in).

The auth flow is driven by a mutable :class:`FakeAuthScenario` so tests can
express "this account needs 2FA", "the code is wrong", "Telegram asks to wait",
and so on. A single shared provider instance can be reused across the multiple
HTTP requests of one wizard flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.app.providers.errors import (
    AuthCodeExpiredError,
    AuthCodeInvalidError,
    PasswordInvalidError,
    SessionInvalidError,
)
from backend.app.providers.types import (
    EntityRef,
    SendCodeResult,
    SignInResult,
    UserIdentity,
)

DEFAULT_CODE = "12345"
DEFAULT_PASSWORD = "password"


@dataclass
class FakeAuthScenario:
    """Controls how a :class:`FakeSessionProvider` behaves.

    All fields have safe defaults so a bare fake "just works" and completes a
    password-less sign-in with :data:`DEFAULT_CODE`.
    """

    identity: UserIdentity = field(
        default_factory=lambda: UserIdentity(
            id=1000001,
            username="fake_user",
            first_name="Fake",
            last_name="User",
            phone="+10000000000",
        )
    )
    expected_code: str = DEFAULT_CODE
    requires_2fa: bool = False
    password: str = DEFAULT_PASSWORD
    # Start "authorized" so health/import paths work without a prior sign-in.
    authorized: bool = True
    # Optional injected failures for the next call of the matching kind.
    send_code_error: Exception | None = None
    sign_in_error: Exception | None = None
    password_error: Exception | None = None
    health_error: Exception | None = None


class FakeSessionProvider:
    """In-memory :class:`SessionProvider` implementation."""

    def __init__(
        self,
        *,
        api_id: str = "",
        api_hash: str = "",
        session_path: Path | None = None,
        scenario: FakeAuthScenario | None = None,
    ) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_path = session_path
        self.scenario = scenario or FakeAuthScenario()
        self.connected = False
        self.closed = True
        self.export_calls = 0

    # --- lifecycle -----------------------------------------------------------
    async def connect(self) -> None:
        self.connected = True
        self.closed = False

    async def aclose(self) -> None:
        self.connected = False
        self.closed = True

    # --- identity ------------------------------------------------------------
    async def get_me(self) -> UserIdentity:
        if self.scenario.health_error is not None:
            raise self.scenario.health_error
        if not self.scenario.authorized:
            raise SessionInvalidError(
                "Аккаунт не авторизован.",
                technical="FakeSessionProvider:not_authorized",
            )
        return self.scenario.identity

    async def health(self) -> UserIdentity:
        return await self.get_me()

    # --- authorization flow --------------------------------------------------
    async def send_code(self, phone: str) -> SendCodeResult:
        if self.scenario.send_code_error is not None:
            raise self.scenario.send_code_error
        return SendCodeResult(
            phone_code_hash=f"fake-hash:{phone}",
            code_type="app",
            next_step="code",
            timeout=60,
        )

    async def sign_in(self, phone: str, code: str, phone_code_hash: str) -> SignInResult:
        if self.scenario.sign_in_error is not None:
            raise self.scenario.sign_in_error
        if not phone_code_hash.startswith("fake-hash:"):
            raise AuthCodeExpiredError(technical="FakeSessionProvider:stale_hash")
        if code != self.scenario.expected_code:
            raise AuthCodeInvalidError(technical="FakeSessionProvider:bad_code")
        if self.scenario.requires_2fa:
            return SignInResult(ok=False, needs_password=True)
        self.scenario.authorized = True
        return SignInResult(ok=True, identity=self.scenario.identity)

    async def sign_in_password(self, password: str) -> SignInResult:
        if self.scenario.password_error is not None:
            raise self.scenario.password_error
        if password != self.scenario.password:
            raise PasswordInvalidError(technical="FakeSessionProvider:bad_password")
        self.scenario.authorized = True
        return SignInResult(ok=True, identity=self.scenario.identity)

    # --- session file --------------------------------------------------------
    async def export_session(self) -> None:
        self.export_calls += 1
        # Simulate Telethon writing the session file so downstream checks and the
        # import/health paths see a real file. Content is a non-secret marker.
        if self._session_path is not None:
            path = self._session_path
            if path.suffix != ".session":
                path = path.with_suffix(".session")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"FAKE-SESSION-PLACEHOLDER")

    # --- extension points (subset; full behaviour lands in PHASE 5/6) --------
    async def resolve_entity(self, username_or_id: str | int) -> EntityRef:
        raw = str(username_or_id).lstrip("@")
        return EntityRef(
            id=abs(hash(raw)) % 10**10,
            username=raw if not raw.lstrip("-").isdigit() else "",
            title=raw,
            kind="channel",
            participants_count=0,
        )

    async def get_participants(
        self, entity: str | int, *, limit: int = 0
    ) -> list[UserIdentity]:
        return []

    async def invite_to_channel(self, entity: str | int, user_id: int) -> None:
        return None


def fake_provider_factory(scenario: FakeAuthScenario | None = None):
    """Return a factory that always builds a fake provider with ``scenario``.

    The same provider instance is reused so a multi-step wizard flow keeps its
    state across requests — mirroring how tests drive the real service.
    """
    shared = FakeSessionProvider(scenario=scenario)

    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        shared._api_id = api_id
        shared._api_hash = api_hash
        shared._session_path = session_path
        return shared

    return _factory


__all__ = [
    "DEFAULT_CODE",
    "DEFAULT_PASSWORD",
    "FakeAuthScenario",
    "FakeSessionProvider",
    "fake_provider_factory",
]
