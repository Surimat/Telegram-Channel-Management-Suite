"""Async engine and session factory.

The engine is created lazily and cached. Tests may override the URL via
``configure_engine`` before first use, or use the :func:`session_scope` helper.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.config import get_settings
from backend.app.db.base import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine (creating it on first use)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.resolve_database_url()
        connect_args = {}
        if url.startswith("sqlite"):
            # Allow use across asyncio tasks/threads used by the app + scheduler.
            connect_args = {"check_same_thread": False}
        _engine = create_async_engine(url, echo=False, future=True, connect_args=connect_args)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def init_models() -> None:
    """Create all tables (used for initial setup / tests)."""
    # Import models so they are registered on Base.metadata.
    from backend.app.db import models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Provide a transactional session scope."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the engine (called on app shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def reset_engine() -> None:
    """Drop cached engine/session factory (used by tests)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
