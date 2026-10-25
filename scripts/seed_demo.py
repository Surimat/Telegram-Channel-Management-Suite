"""Seed a self-contained demo dataset for the Windows test/demo kit.

This is a **test-only** helper. It is guarded: it refuses to run unless
``APP_ENV=demo`` in the environment, so it can never touch a real installation.

It is idempotent: running it twice does not duplicate anything.

What it creates (no secrets, no external calls):

* one demo channel (registry row) with modules configured;
* one demo bot and a verified posting binding, so the Setup Wizard's
  "bot and rights" step is genuinely verified;
* one demo content source and two ready materials;
* the built-in AI profiles and one declarative automation rule;
* then it runs every Setup Wizard step so the wizard shows real results.

Run it from the application root (the folder that holds ``.env``)::

    python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def _ensure_importable() -> None:
    """Make the application importable from the repo and the packaged layout."""
    here = Path(__file__).resolve()
    for candidate in (here.parents[1], here.parents[1] / "app"):
        if (candidate / "backend").is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            return


_ensure_importable()

DEMO_CHANNEL_REFERENCE = "@demo_news"
DEMO_BOT_USERNAME = "demo_manager_bot"
DEMO_SOURCE_REFERENCE = "demo://materials"


def _refuse(message: str) -> None:
    print(f"[demo] {message}")
    raise SystemExit(2)


async def _seed() -> int:
    from backend.app.core.config import get_settings

    settings = get_settings()
    if settings.app_env != "demo":
        _refuse(
            "APP_ENV is not 'demo' — refusing to seed. "
            "This helper only runs in the demo kit."
        )

    from sqlalchemy import select

    from backend.app.core import paths
    from backend.app.db import models as _models  # noqa: F401  (registers models)
    from backend.app.db.base import Base, utcnow  # noqa: F401  (registers models)
    from backend.app.db.migrate import upgrade_database
    from backend.app.db.models.binding import (
        FUNCTION_POSTING,
        BindingRole,
        BindingStatus,
        BotChannelBinding,
    )
    from backend.app.db.models.bot import Bot, BotHealth, BotKind
    from backend.app.db.models.channel import Channel, ChannelKind, ChannelStatus
    from backend.app.db.models.content import (
        ContentItem,
        ContentItemStatus,
        ContentSource,
        ContentSourceKind,
        ContentSourceStatus,
    )
    from backend.app.db.session import get_session_factory, session_scope
    from backend.app.services.ai_profiles import AiProfileService
    from backend.app.services.automation_rules import AutomationRuleService
    from backend.app.services.setup_wizard import STEP_KEYS, SetupWizardService

    # Ensure predictable runtime directories exist (notably data/ for SQLite)
    # before the engine opens the database file.
    for ensure in (
        paths.data_dir,
        paths.sessions_dir,
        paths.backups_dir,
        paths.logs_dir,
        paths.exports_dir,
    ):
        ensure()

    # Ensure the schema exists (safe on a fresh install; stamps a legacy DB).
    await upgrade_database()

    factory = get_session_factory()

    async with factory() as session:
        existing = (
            await session.execute(
                select(Channel).where(Channel.reference == DEMO_CHANNEL_REFERENCE)
            )
        ).scalar_one_or_none()
        if existing is not None:
            print("[demo] Demo data already present — nothing to do.")
            return 0

    async with session_scope() as session:
        channel = Channel(
            reference=DEMO_CHANNEL_REFERENCE,
            title="Демо-канал «Новости»",
            username="demo_news",
            kind=ChannelKind.CHANNEL,
            status=ChannelStatus.VERIFIED,
            is_default=True,
            modules='{"reactions": true, "audience": true, "invites": true, "analytics": true}',
            verification_status="ok",
            verification_message="Демонстрационная проверка доступа (без Telegram).",
            verification_hint="",
            participants_count=12345,
            last_verified_at=utcnow(),
            note="Тестовый канал демо-сборки.",
        )
        session.add(channel)
        await session.flush()

        bot = Bot(
            kind=BotKind.MANAGER,
            enabled=True,
            username=DEMO_BOT_USERNAME,
            title="Демо-бот",
            health=BotHealth.OK,
            health_message="Демонстрационный бот (без реального токена).",
        )
        session.add(bot)
        await session.flush()

        session.add(
            BotChannelBinding(
                bot_id=bot.id,
                channel_id=channel.id,
                channel_label=channel.title,
                function=FUNCTION_POSTING,
                status=BindingStatus.READY,
                role=BindingRole.ADMINISTRATOR,
                can_post_messages=True,
                can_edit_messages=True,
                can_delete_messages=True,
                can_manage_chat=True,
                can_invite_users=True,
                can_set_reactions=True,
                note="Демонстрационная привязка.",
            )
        )

        source = ContentSource(
            kind=ContentSourceKind.MANUAL,
            reference=DEMO_SOURCE_REFERENCE,
            title="Демо-источник",
            enabled=True,
            status=ContentSourceStatus.OK,
            channel_id=channel.id,
        )
        session.add(source)
        await session.flush()

        session.add_all(
            [
                ContentItem(
                    title="Демо-материал 1",
                    text=(
                        "Это демонстрационный материал. Он показывает, как выглядит "
                        "готовый к публикации пост в Content Studio."
                    ),
                    cleaned_text="",
                    status=ContentItemStatus.READY,
                    source_id=source.id,
                    source_channel=channel.reference,
                    language="ru",
                    source_language="ru",
                ),
                ContentItem(
                    title="Демо-материал 2",
                    text=(
                        "Второй демонстрационный материал. Проверьте календарь, "
                        "правила и панель канала."
                    ),
                    cleaned_text="",
                    status=ContentItemStatus.APPROVED,
                    source_id=source.id,
                    source_channel=channel.reference,
                    language="ru",
                    source_language="ru",
                ),
            ]
        )

        await AiProfileService(session).ensure_builtin()

        rule_service = AutomationRuleService(session)
        if not await rule_service.list_rules():
            await rule_service.create(
                name="Демо-правило: длинные тексты на проверку",
                source_kind="",
                condition={"min_length": 200},
                actions=["classify", "review"],
                profile_key="news",
                priority=10,
                description="Демонстрационное правило: длинный материал уходит на проверку.",
            )

    # Run every wizard step so the owner sees real (not guessed) results.
    async with session_scope() as session:
        wizard = SetupWizardService(session)
        for key in STEP_KEYS:
            try:
                await wizard.run_step(key)
            except Exception as exc:
                print(f"[demo] step '{key}' could not run: {exc}")
        view = await wizard.state()
        print(
            f"[demo] Setup Wizard: {view.completed_steps}/{view.total_steps} шагов "
            f"подтверждено ({view.progress_percent}%)."
        )

    print("[demo] Demo data ready.")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_seed()))


if __name__ == "__main__":
    main()
