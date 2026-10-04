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
    FloodWaitError,
    PasswordInvalidError,
    SessionInvalidError,
)
from backend.app.providers.types import (
    EntityRef,
    ParticipantPage,
    PermissionReport,
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


@dataclass
class FakeAudienceScenario:
    """Controls the fake participant scan (PHASE 5).

    ``participants`` is the full list the fake pretends to hold; pages are served
    from it in ``page_size`` chunks. When ``reported_total`` is larger than the
    served list, the fake simulates Telegram hiding part of the audience so the
    ``PARTIAL`` completeness path can be exercised without a real account.
    """

    participants: list[UserIdentity] = field(default_factory=list)
    reported_total: int | None = None
    page_size: int = 100
    # When set, resolving the entity raises this (e.g. EntityNotFoundError).
    resolve_error: Exception | None = None
    # When set, fetching participants raises this (e.g. FloodWaitError).
    participants_error: Exception | None = None
    # When True, the entity reports a hidden participant list (NO_ACCESS).
    participants_hidden: bool = False
    # Entity title/kind returned by resolve for any input.
    title: str = "Fake Source"
    kind: str = "channel"


@dataclass
class FakeInviteScenario:
    """Controls how the fake reacts to :meth:`invite_to_channel` (PHASE 6).

    ``default_error`` fails every invite by default; ``errors_by_user`` overrides
    that for specific Telegram user ids (e.g. a privacy-restricted user), and
    ``error_after`` fails only once the given number of invites has succeeded —
    handy for exercising a FloodWait partway through a run. ``record`` captures
    the invited user ids so tests can assert exactly what was attempted.
    """

    default_error: Exception | None = None
    errors_by_user: dict[int, Exception] = field(default_factory=dict)
    error_after: int | None = None
    record: list[int] = field(default_factory=list)


@dataclass
class FakePermissionScenario:
    """Controls how the fake reacts to :meth:`probe_permissions` (post-1.0).

    Every flag maps to a real outcome so the whole permission UI/logic can be
    tested without Telegram. ``resolve_error`` simulates "channel not found";
    ``participants_hidden`` simulates a channel whose member list Telegram hides.
    """

    # When set, resolving the channel raises this (e.g. EntityNotFoundError).
    resolve_error: Exception | None = None
    authorized: bool = True
    participants_hidden: bool = False
    can_invite: bool = False
    participants_count: int | None = 1234
    title: str = "Fake Channel"
    username: str = "fakechannel"
    kind: str = "channel"
    # When set, the participants step raises this (FloodWait/privacy).
    participants_error: Exception | None = None


@dataclass
class FakeDiscoveryScenario:
    """Controls the fake public search (v1.1 donor discovery).

    ``channels`` is the list of channels the fake pretends Telegram returned for
    any query. ``search_error`` simulates an error (e.g. FloodWait). When
    ``channels`` is empty the search honestly returns nothing.
    """

    channels: list[dict[str, object]] = field(default_factory=list)
    search_error: Exception | None = None


def make_fake_users(count: int, *, start_id: int = 1) -> list[UserIdentity]:
    """Build a deterministic list of fake users for scan tests."""
    users: list[UserIdentity] = []
    for i in range(count):
        uid = start_id + i
        users.append(
            UserIdentity(
                id=uid,
                username=f"user{uid}",
                first_name="User",
                last_name=str(uid),
            )
        )
    return users


def _page(
    users: list[UserIdentity], total: int | None, exhausted: bool
) -> ParticipantPage:
    return ParticipantPage(users=users, total=total, exhausted=exhausted)


class FakeSessionProvider:
    """In-memory :class:`SessionProvider` implementation."""

    def __init__(
        self,
        *,
        api_id: str = "",
        api_hash: str = "",
        session_path: Path | None = None,
        scenario: FakeAuthScenario | None = None,
        audience: FakeAudienceScenario | None = None,
        invite: FakeInviteScenario | None = None,
        permission: FakePermissionScenario | None = None,
        discovery: FakeDiscoveryScenario | None = None,
    ) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_path = session_path
        self.scenario = scenario or FakeAuthScenario()
        self.audience = audience or FakeAudienceScenario()
        self.invite = invite or FakeInviteScenario()
        self.permission = permission or FakePermissionScenario()
        self.discovery = discovery or FakeDiscoveryScenario()
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

    async def import_string_session(self, value: str, target_path: Path) -> None:
        """Persist a placeholder session file for a StringSession (offline mode)."""
        if not value:
            raise SessionInvalidError(technical="FakeSessionProvider:empty_string_session")
        target = target_path
        if target.suffix != ".session":
            target = target.with_suffix(".session")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"FAKE-STRING-SESSION-PLACEHOLDER")

    # --- extension points (subset; full behaviour lands in PHASE 5/6) --------
    async def resolve_entity(self, username_or_id: str | int) -> EntityRef:
        if self.audience.resolve_error is not None:
            raise self.audience.resolve_error
        raw = str(username_or_id).lstrip("@")
        return EntityRef(
            id=abs(hash(raw)) % 10**10,
            username=raw if not raw.lstrip("-").isdigit() else "",
            title=self.audience.title or raw,
            kind=self.audience.kind,
            participants_count=self._reported_total(),
            participants_hidden=self.audience.participants_hidden,
        )

    async def get_participants(
        self, entity: str | int, *, limit: int = 0
    ) -> list[UserIdentity]:
        users = list(self.audience.participants)
        if limit > 0:
            users = users[:limit]
        return users

    async def iter_participant_pages(
        self,
        entity: str | int,
        *,
        batch_size: int = 100,
        offset: int = 0,
        limit: int = 0,
    ) -> list[ParticipantPage]:
        if self.audience.participants_error is not None:
            raise self.audience.participants_error
        if self.audience.participants_hidden:
            return [_page([], self._reported_total(), exhausted=True)]
        users = list(self.audience.participants)
        page_size = max(1, min(batch_size, self.audience.page_size))
        if limit > 0:
            users = users[:limit]
        total = self._reported_total()
        if offset >= len(users):
            return [_page([], total, exhausted=True)]
        window = users[offset : offset + page_size]
        exhausted = offset + len(window) >= len(users)
        return [_page(window, total, exhausted=exhausted)]

    def _reported_total(self) -> int | None:
        if self.audience.reported_total is not None:
            return self.audience.reported_total
        if self.audience.participants:
            return len(self.audience.participants)
        return None

    async def invite_to_channel(self, entity: str | int, user_id: int) -> None:
        scenario = self.invite
        self.invite.record.append(int(user_id))
        if user_id in scenario.errors_by_user:
            raise scenario.errors_by_user[user_id]
        if scenario.default_error is not None:
            raise scenario.default_error
        if scenario.error_after is not None:
            ok = sum(1 for uid in scenario.record if uid not in scenario.errors_by_user)
            if ok > scenario.error_after:
                raise scenario.default_error or FloodWaitError(30)
        return None

    # --- permission probe (post-1.0 hardening) -------------------------------
    async def probe_permissions(self, entity: str | int) -> PermissionReport:
        p = self.permission
        if not p.authorized or not self.scenario.authorized:
            return PermissionReport(
                status="auth_required",
                message="Аккаунт не авторизован.",
                how_to_fix="Авторизуйте аккаунт в разделе «Аккаунты».",
            )
        if p.resolve_error is not None:
            raise p.resolve_error
        report = PermissionReport(
            status="privacy_restricted",
            authorized=True,
            session_ok=True,
            channel_found=True,
            can_read_info=True,
            channel_id=abs(hash(str(entity))) % 10**10,
            channel_title=p.title,
            channel_username=p.username,
            channel_kind=p.kind,
            participants_count=p.participants_count,
        )
        if p.participants_error is not None:
            raise p.participants_error
        report.can_read_participants = not p.participants_hidden
        report.can_invite = p.can_invite
        if report.can_invite:
            report.status = "ok"
            report.message = "Канал доступен, приглашения разрешены."
        elif report.can_read_participants:
            report.status = "partial"
            report.message = (
                "Канал доступен и список участников виден, но приглашать "
                "может только администратор."
            )
            report.how_to_fix = "Выдайте аккаунту права администратора с правом приглашать."
        else:
            report.status = "privacy_restricted"
            report.message = (
                "Канал доступен, но Telegram не предоставляет список участников "
                "этому аккаунту."
            )
            report.how_to_fix = "Используйте публичный источник или аккаунт с доступом."
        return report

    # --- public search (v1.1 donor discovery) --------------------------------
    async def search_public(self, query: str, *, limit: int = 20) -> list[EntityRef]:
        scenario = self.discovery
        if scenario.search_error is not None:
            raise scenario.search_error
        if not (query or "").strip():
            return []
        refs: list[EntityRef] = []
        for i, item in enumerate(scenario.channels[: max(1, limit)]):
            username = str(item.get("username", "") or "")
            refs.append(
                EntityRef(
                    id=int(item.get("id", 900000 + i) or 900000 + i),
                    username=username,
                    title=str(item.get("title", "") or username),
                    kind=str(item.get("kind", "channel") or "channel"),
                    participants_count=int(item.get("subscribers", 0) or 0),
                    subscribers=int(item.get("subscribers", 0) or 0),
                    avg_views=float(item.get("avg_views", 0.0) or 0.0),
                    language=str(item.get("language", "") or ""),
                )
            )
        return refs


def fake_provider_factory(scenario: FakeAuthScenario | None = None):
    """Return a factory that always builds a fake provider with ``scenario``.

    The same provider instance is reused so a multi-step wizard flow keeps its
    state across requests — mirroring how tests drive the real service.
    """
    shared = FakeSessionProvider(scenario=scenario)

    def _factory(
        *,
        api_id="",
        api_hash="",
        session_path=None,
        provider_name="auto",
        settings=None,
        proxy=None,
    ):
        shared._api_id = api_id
        shared._api_hash = api_hash
        shared._session_path = session_path
        return shared

    return _factory


def fake_audience_factory(
    audience: FakeAudienceScenario | None = None,
    scenario: FakeAuthScenario | None = None,
):
    """Return a session-provider factory whose fake serves ``audience``.

    Letting the same shared provider back both the Session Manager and the
    Audience Scanner mirrors production, where one account drives both.
    """
    shared = FakeSessionProvider(scenario=scenario, audience=audience)

    def _factory(
        *,
        api_id="",
        api_hash="",
        session_path=None,
        provider_name="auto",
        settings=None,
        proxy=None,
    ):
        shared._api_id = api_id
        shared._api_hash = api_hash
        shared._session_path = session_path
        return shared

    return _factory


__all__ = [
    "DEFAULT_CODE",
    "DEFAULT_PASSWORD",
    "FakeAudienceScenario",
    "FakeAuthScenario",
    "FakeDiscoveryScenario",
    "FakeInviteScenario",
    "FakePermissionScenario",
    "FakeSessionProvider",
    "fake_audience_factory",
    "fake_provider_factory",
    "make_fake_users",
]
