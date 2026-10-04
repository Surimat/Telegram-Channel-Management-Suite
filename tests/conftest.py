"""Shared pytest fixtures.

Each test gets an isolated temporary SQLite database and fresh settings so tests
never touch real data or secrets.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("TCMS_ROOT", str(Path(__file__).resolve().parents[1]))

@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app at temporary data/sessions/logs and a temp DB."""
    monkeypatch.setenv("TCMS_ROOT", str(tmp_path))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key-value-0123456789")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("MANAGER_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))

    from backend.app.core import paths
    from backend.app.core.config import reset_settings_cache
    from backend.app.db.session import reset_engine

    reset_settings_cache()
    reset_engine()
    if hasattr(paths.project_root, "cache_clear"):
        paths.project_root.cache_clear()
    yield
    reset_settings_cache()
    reset_engine()
    if hasattr(paths.project_root, "cache_clear"):
        paths.project_root.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_between_tests(_isolated_env) -> AsyncIterator[None]:
    """Close all DB connections after each test to avoid GC warnings.

    Depends on ``_isolated_env`` so it is set up *after* it and therefore torn
    down *before* it: the engine must be disposed (in the test's event loop)
    before ``_isolated_env`` resets it, otherwise open connections are garbage
    collected on a closed loop and can fail the next test.
    """
    yield
    from backend.app.db.session import dispose_engine

    await dispose_engine()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Trigger lifespan-less startup work needed for DB models.
        yield ac


def make_fake_provider_factory():
    """Return a provider factory that always builds the deterministic fake."""
    from backend.app.providers.fake_bot import FakeTelegramBotProvider

    def _factory(token, *, provider_name="auto", settings=None):
        return FakeTelegramBotProvider(token)

    return _factory


def make_fake_session_factory(scenario=None, permission=None):
    """Return a session-provider factory building a shared fake provider.

    A single provider instance is reused across requests so a multi-step wizard
    flow (start → code → password) keeps its state, exactly like the real one.
    """
    from backend.app.providers.fake_session import FakeAuthScenario, FakeSessionProvider

    shared = FakeSessionProvider(scenario=scenario or FakeAuthScenario())
    if permission is not None:
        shared.permission = permission

    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        shared._api_id = api_id
        shared._api_hash = api_hash
        shared._session_path = session_path
        return shared

    return _factory


def make_fake_audience_service_factory(audience=None, scenario=None):
    """Return a session-provider factory whose fake also serves audience data."""
    from backend.app.providers.fake_session import (
        FakeAudienceScenario,
        FakeAuthScenario,
        FakeSessionProvider,
    )

    shared = FakeSessionProvider(
        scenario=scenario or FakeAuthScenario(),
        audience=audience or FakeAudienceScenario(),
    )

    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        shared._api_id = api_id
        shared._api_hash = api_hash
        shared._session_path = session_path
        return shared

    return _factory


@pytest_asyncio.fixture
async def audience_client() -> AsyncIterator[AsyncClient]:
    """API client with sessions+audience wired to a fake that serves members."""
    from backend.app.api.deps import get_session_provider_factory
    from backend.app.db.models.session import SessionStatus, UserSession
    from backend.app.db.session import init_models, session_scope
    from backend.app.main import create_app
    from backend.app.providers.fake_session import FakeAudienceScenario, make_fake_users

    await init_models()
    async with session_scope() as session:
        session.add(
            UserSession(
                telegram_user_id=1000001,
                username="fake_user",
                display_name="Fake User",
                status=SessionStatus.ONLINE,
                enabled=True,
                api_id="1",
            )
        )
    app = create_app()
    factory = make_fake_audience_service_factory(
        audience=FakeAudienceScenario(participants=make_fake_users(120), page_size=50)
    )
    app.dependency_overrides[get_session_provider_factory] = lambda: factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def bot_client() -> AsyncIterator[AsyncClient]:
    """API client with Telegram access wired to the fake provider.

    Real credentials and network are never needed (decision D-001).
    """
    from backend.app.api.deps import get_provider_factory
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    factory = make_fake_provider_factory()
    app.dependency_overrides[get_provider_factory] = lambda: factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def make_fake_invite_session_factory(invite=None, audience=None, scenario=None):
    """Return a session-provider factory whose fake serves audience + invites."""
    from backend.app.providers.fake_session import (
        FakeAudienceScenario,
        FakeAuthScenario,
        FakeInviteScenario,
        FakeSessionProvider,
    )

    shared = FakeSessionProvider(
        scenario=scenario or FakeAuthScenario(),
        audience=audience or FakeAudienceScenario(),
        invite=invite or FakeInviteScenario(),
    )

    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        return shared

    return _factory


@pytest_asyncio.fixture
async def invite_client() -> AsyncIterator[AsyncClient]:
    """API client with sessions/audience/invites wired to a deterministic fake."""
    from backend.app.api.deps import get_session_provider_factory
    from backend.app.db.models.audience import AudienceUser
    from backend.app.db.models.session import SessionStatus, UserSession
    from backend.app.db.session import init_models, session_scope
    from backend.app.main import create_app
    from backend.app.providers.fake_session import FakeAudienceScenario, make_fake_users

    await init_models()
    async with session_scope() as session:
        session.add(
            UserSession(
                telegram_user_id=1000001,
                username="fake_user",
                display_name="Fake User",
                status=SessionStatus.ONLINE,
                enabled=True,
                api_id="1",
            )
        )
        for i in range(5):
            session.add(
                AudienceUser(
                    telegram_user_id=2000 + i,
                    username=f"member{i}",
                    display_name=f"Member {i}",
                )
            )
    app = create_app()
    factory = make_fake_invite_session_factory(
        audience=FakeAudienceScenario(participants=make_fake_users(5), page_size=50)
    )
    app.dependency_overrides[get_session_provider_factory] = lambda: factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def session_client() -> AsyncIterator[AsyncClient]:
    """API client with MTProto access wired to the fake session provider."""
    from backend.app.api.deps import get_session_provider_factory
    from backend.app.db.session import init_models
    from backend.app.main import create_app

    await init_models()
    app = create_app()
    factory = make_fake_session_factory()
    app.dependency_overrides[get_session_provider_factory] = lambda: factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def permission_client() -> AsyncIterator[AsyncClient]:
    """API client for the permission probe, wired to a fake with real access."""
    from backend.app.api.deps import get_session_provider_factory
    from backend.app.db.session import init_models
    from backend.app.main import create_app
    from backend.app.providers.fake_session import FakePermissionScenario

    await init_models()
    app = create_app()
    factory = make_fake_session_factory(permission=FakePermissionScenario(can_invite=True))
    app.dependency_overrides[get_session_provider_factory] = lambda: factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def manager_client() -> AsyncIterator[AsyncClient]:
    """API client with the manager bot provider wired to the deterministic fake."""
    from backend.app.api.deps import get_provider_factory
    from backend.app.db.session import init_models
    from backend.app.main import create_app
    from backend.app.providers.fake_bot import FakeTelegramBotProvider

    await init_models()
    app = create_app()

    def _factory(token, *, provider_name="auto", settings=None):
        return FakeTelegramBotProvider(token)

    app.dependency_overrides[get_provider_factory] = lambda: _factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def channel_client() -> AsyncIterator[AsyncClient]:
    """API client for the Channel Registry, wired to a fake with real access.

    Uses the same fake session provider as the permission probe so verification
    succeeds without any network or real Telegram account.
    """
    from backend.app.api.deps import get_session_provider_factory
    from backend.app.db.session import init_models
    from backend.app.main import create_app
    from backend.app.providers.fake_session import FakePermissionScenario

    await init_models()
    app = create_app()
    factory = make_fake_session_factory(permission=FakePermissionScenario(can_invite=True))
    app.dependency_overrides[get_session_provider_factory] = lambda: factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
