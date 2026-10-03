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
async def _dispose_engine_between_tests() -> AsyncIterator[None]:
    """Close all DB connections after each test to avoid GC warnings."""
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
