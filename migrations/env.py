"""Alembic migration environment.

The database URL is resolved at runtime from the application settings
(``backend.app.core.config``), so migrations follow the same rules as the app:
``.env`` → ``DATABASE_URL``/``TCMS_ROOT`` → portable directory layout. Nothing
secret is written to ``alembic.ini``.

Both offline and online modes are supported. Migrations run in a **transaction**
(``transaction_per_migration``), so a failure rolls back instead of leaving a
half-applied schema. The guarded runner in ``backend/app/db/migrate.py`` takes a
backup before applying risky steps.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from backend.app.core.config import get_settings
from backend.app.db.base import Base

# Import the model package so every table is registered on Base.metadata.
from backend.app.db import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the real database URL from application settings at runtime.
config.set_main_option("sqlalchemy.url", get_settings().resolve_database_url())

target_metadata = Base.metadata


def _configure(connection: Connection | None = None) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect column type/server_default drift between models and migrations.
        compare_type=True,
        compare_server_default=True,
        # SQLite needs batch mode for ALTER-heavy migrations.
        render_as_batch=connection is not None and connection.dialect.name == "sqlite",
        # Apply each migration in its own transaction where the backend allows.
        transaction_per_migration=True,
    )


def run_migrations_offline() -> None:
    """Render SQL for the migrations without a live DB connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine from the resolved URL and run migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
