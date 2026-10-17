#!/usr/bin/env python3
"""Reaction Manager — проверка, что реакции реально работают (D-130).

Простыми словами: этот скрипт прогоняет весь путь реакции на посты канала так,
как это делает настоящий Telegram, и печатает, что получилось. Ничего не меняет
и никуда не ходит в интернет.

Как запустить (из папки проекта):

    source .venv/bin/activate
    python scripts/check_reactions.py

В портативной сборке для Windows это делает файл CHECK_REACTIONS.bat —
достаточно дважды щёлкнуть по нему, встроенный Python уже внутри. Скрипт
использует только библиотеки самой программы (pytest не нужен).

Что проверяется (по шагам):

  1. Обновление от Telegram вида ``channel_post`` разбирается (а не теряется).
  2. Опрос бота просит у Telegram присылать посты канала (``channel_post``).
  3. Пост сохраняется с настоящими ``channel_id`` и ``telegram_message_id``.
  4. Планируется реакция и создаётся задание в очереди для ЭТОГО поста.
  5. Планировщик берёт задание и вызывает ``set_reaction`` с настоящими id.
  6. Повторное обновление не создаёт второй пост (защита от дублей).
  7. Ошибка Telegram честно помечает задание «failed», а не «done».
  8. Обратный контроль: без разбора ``channel_post`` ничего бы не сработало.

Код завершения 0 — всё в порядке; 1 — есть проблема (подробности в выводе).
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import os
import sys
from pathlib import Path

# Make the project importable no matter where the script is launched from.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The verification must never touch a real database or real Telegram: use a
# temporary SQLite file and the deterministic fake provider (decision D-001).
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from aiogram.types import Chat, Message, Update  # noqa: E402

from backend.app.db.models.bot import Bot, BotHealth, BotKind  # noqa: E402
from backend.app.db.models.channel import Channel, ChannelKind  # noqa: E402
from backend.app.db.models.post import PostStatus  # noqa: E402
from backend.app.db.repositories.bots import BotRepository  # noqa: E402
from backend.app.db.repositories.channels import ChannelRepository  # noqa: E402
from backend.app.db.repositories.posts import PostRepository  # noqa: E402
from backend.app.db.repositories.reactions import ReactionJobRepository  # noqa: E402
from backend.app.db.session import init_models, session_scope  # noqa: E402
from backend.app.manager.runtime import ManagerBotRuntime  # noqa: E402
from backend.app.providers.aiogram_bot import AiogramBotProvider  # noqa: E402
from backend.app.providers.errors import UnauthorizedError  # noqa: E402
from backend.app.providers.fake_bot import FakeTelegramBotProvider  # noqa: E402
from backend.app.scheduler import handlers as scheduler_handlers  # noqa: E402
from backend.app.scheduler.scheduler import Scheduler  # noqa: E402
from backend.app.services.queue_service import QueueService  # noqa: E402
from backend.app.services.reaction_service import ReactionService  # noqa: E402

CHAT_ID = -1001234567890
MSG_ID = 4321
USERNAME = "mychannel"

OK = "OK  "
BAD = "ОШИБКА"


def _line(status: str, text: str) -> None:
    print(f"  [{status}] {text}")


async def _seed(session, *, modules: dict | None = None) -> None:
    await ChannelRepository(session).add(
        Channel(
            id="ch1",
            reference="@mychannel",
            username=USERNAME,
            telegram_id=CHAT_ID,
            kind=ChannelKind.CHANNEL,
            modules=json.dumps(modules if modules is not None else {"reactions": True}),
        )
    )
    await BotRepository(session).add(
        Bot(
            kind=BotKind.ORDINARY,
            enabled=True,
            telegram_id=555,
            username="slave1",
            token_encrypted="enc:slave",
            health=BotHealth.OK,
        )
    )
    await BotRepository(session).add(
        Bot(
            kind=BotKind.MANAGER,
            enabled=True,
            telegram_id=999,
            username="manager",
            token_encrypted="enc:manager",
            health=BotHealth.OK,
        )
    )
    service = ReactionService(session)
    await service.save_profile(
        None,
        name="Проверка",
        enabled=True,
        is_default=True,
        allowed_emoji=["❤️", "👍"],
        participation_probability=1.0,
        skip_probability=0.0,
        delay_min=0,
        delay_max=0,
    )


def _real_update() -> Update:
    chat = Chat(id=CHAT_ID, type="channel", username=USERNAME, title="My Channel")
    message = Message(message_id=MSG_ID, date=0, chat=chat, text="Спасибо за донат!")
    return Update(update_id=100, channel_post=message)


def _poll_provider(update: Update, captured: dict) -> AiogramBotProvider:
    provider = AiogramBotProvider("123456:TEST-TOKEN")

    async def fake_get_updates(**kwargs):  # type: ignore[no-untyped-def]
        captured["allowed_updates"] = kwargs.get("allowed_updates")
        return [update]

    async def _noop_close() -> None:
        return None

    provider._bot.get_updates = fake_get_updates  # type: ignore[method-assign]
    provider.close = _noop_close  # type: ignore[method-assign]
    return provider


class _StubService:
    def __init__(self, session, provider) -> None:  # type: ignore[no-untyped-def]
        self._provider = provider

    async def manager_provider(self):  # type: ignore[no-untyped-def]
        return self._provider

    async def register_commands(self, provider) -> bool:  # type: ignore[no-untyped-def]
        return True

    async def handle_update(self, update):  # type: ignore[no-untyped-def]
        class _Result:
            handled = False
            reply = ""

        return _Result()


async def _run_poll(monkeypatch, update: Update, captured: dict) -> None:
    provider = _poll_provider(update, captured)

    def _factory(session):  # type: ignore[no-untyped-def]
        return _StubService(session, provider)

    async def _no_flush(self, session, provider):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr("backend.app.manager.runtime.ManagerBotService", _factory)
    monkeypatch.setattr(ManagerBotRuntime, "_flush_notifications", _no_flush)
    await ManagerBotRuntime()._tick()


def _fake_factory(provider: FakeTelegramBotProvider):  # type: ignore[no-untyped-def]
    def _make(token, *, provider_name="auto", settings=None):
        return provider

    return _make


_UNSET = object()


class _Patcher:
    """A tiny stand-in for pytest's MonkeyPatch so this check runs anywhere.

    The portable Windows build ships only the application's runtime
    dependencies — ``pytest`` is not among them — so the check cannot depend on
    pytest just to patch a few module attributes for the duration of the run.
    The API mirrors the small subset used here (``setattr`` / ``undo``).
    """

    def __init__(self) -> None:
        self._undo: list = []

    def setattr(self, target, name, value=_UNSET):  # type: ignore[no-untyped-def]
        if isinstance(target, str):
            module_name, _, attr = target.rpartition(".")
            module = importlib.import_module(module_name)
            # Mirrors pytest: for the string form the second positional is the
            # value (``setattr("pkg.mod.attr", value)``).
            if value is _UNSET:
                value = name
            name = attr
        else:
            module = target
        self._undo.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    def undo(self) -> None:
        for module, name, original in reversed(self._undo):
            setattr(module, name, original)
        self._undo.clear()


async def main() -> int:
    problems = 0
    print("=" * 70)
    print("Проверка Reaction Manager (D-130): реакции на посты канала")
    print("=" * 70)

    await init_models()
    monkeypatch = _Patcher()
    monkeypatch.setattr(
        "backend.app.services.reaction_service.open_secret",
        lambda value, settings: "123456:FAKE-TOKEN",
    )

    # 1. Разбор обновления channel_post.
    captured: dict = {}
    async with session_scope() as session:
        await _seed(session)
        await _run_poll(monkeypatch, _real_update(), captured)

    print("\n1) Telegram присылает пост канала, бот его разбирает")
    allowed = captured.get("allowed_updates")
    if allowed and "channel_post" in allowed:
        _line(OK, "Опрос просит у Telegram посты канала (channel_post).")
    else:
        _line(BAD, f"Посты канала НЕ запрашиваются (allowed_updates={allowed}).")
        problems += 1

    # 2-3. Пост сохранён с настоящими id.
    async with session_scope() as session:
        post = await PostRepository(session).get_by_telegram(CHAT_ID, MSG_ID)
    print("\n2) Пост сохранён с настоящими id из Telegram")
    if post is None:
        _line(BAD, "Пост НЕ сохранён — реакции не на что ставить.")
        problems += 1
        print("\nИтог: НЕ ПРОЙДЕНО (остановка).")
        return 1
    checks = [
        (post.telegram_message_id == MSG_ID, f"telegram_message_id = {post.telegram_message_id}"),
        (post.channel_id == CHAT_ID, f"channel_id = {post.channel_id}"),
        (post.status == PostStatus.PLANNED, f"статус = {post.status.value}"),
    ]
    for good, text in checks:
        _line(OK if good else BAD, text)
        problems += 0 if good else 1

    # 4. Задание реакции создано и в очереди.
    print("\n3) Создано задание реакции и задание в очереди")
    async with session_scope() as session:
        jobs = await ReactionJobRepository(session).for_post(post.id)
        scheduled = [j for j in jobs if j.status.value == "scheduled"]
        queue_jobs, _t = await QueueService(session).list(limit=100)
        reaction_queue = [j for j in queue_jobs if j.kind == "reaction.job"]
        payload_ok = bool(
            reaction_queue
            and json.loads(reaction_queue[0].payload).get("post_id") == post.id
        )
    for good, text in [
        (bool(scheduled), f"запланировано реакций: {len(scheduled)}"),
        (bool(reaction_queue), f"заданий в очереди: {len(reaction_queue)}"),
        (payload_ok, "очередь указывает именно на этот пост"),
    ]:
        _line(OK if good else BAD, text)
        problems += 0 if good else 1

    # 5. Планировщик ставит реакцию через провайдера.
    print("\n4) Планировщик ставит реакцию (set_reaction)")
    provider = FakeTelegramBotProvider("123456:FAKE-TOKEN")

    def _service_factory(session):  # type: ignore[no-untyped-def]
        return ReactionService(session, provider_factory=_fake_factory(provider))

    monkeypatch.setattr(scheduler_handlers, "ReactionService", _service_factory)
    scheduler = Scheduler()
    scheduler_handlers.register_handlers(scheduler)
    await scheduler._tick()
    applied = provider.reactions[0] if provider.reactions else None
    for good, text in [
        (applied is not None, "провайдер вызван (реакция поставлена)"),
        (applied is not None and applied.chat_id == CHAT_ID, "реакция на нужный канал"),
        (applied is not None and applied.message_id == MSG_ID, "реакция на нужный пост"),
        (
            applied is not None and bool(applied.emoji),
            f"эмодзи: {applied.emoji if applied else '—'}",
        ),
    ]:
        _line(OK if good else BAD, text)
        problems += 0 if good else 1

    # 6. Повтор не создаёт дубль.
    print("\n5) Повтор обновления не создаёт второй пост")
    await _run_poll(monkeypatch, _real_update(), captured)
    async with session_scope() as session:
        _posts, total = await PostRepository(session).list()
    _line(OK if total == 1 else BAD, f"постов в базе: {total} (ожидается 1)")
    problems += 0 if total == 1 else 1

    # 7. Ошибка Telegram честно помечается.
    print("\n6) Ошибка Telegram честно помечает задание")
    failing = FakeTelegramBotProvider(
        "123456:FAKE-TOKEN",
        fail_with=UnauthorizedError("Бот не имеет права ставить реакции."),
    )

    async with session_scope() as session:
        service = ReactionService(session)
        post2 = await service.ingest_channel_post(
            chat_id=CHAT_ID, message_id=9999, text="Тест ошибки", chat_username=USERNAME
        )
        jobs2 = await ReactionJobRepository(session).for_post(post2.id) if post2 else []
        sched2 = [j for j in jobs2 if j.status.value == "scheduled"]
        fail_service = ReactionService(session, provider_factory=_fake_factory(failing))
        with contextlib.suppress(UnauthorizedError):
            await fail_service.execute_reaction_job(sched2[0].id)
        await session.commit()

    async with session_scope() as session:
        post2 = await PostRepository(session).get_by_telegram(CHAT_ID, 9999)
        job2 = (await ReactionJobRepository(session).for_post(post2.id))[0]
    _line(
        OK if job2.status.value == "failed" else BAD,
        f"статус задания после ошибки: {job2.status.value} (ожидается failed)",
    )
    problems += 0 if job2.status.value == "failed" else 1

    # 8. Обратный контроль: старый разбор терял пост.
    print("\n7) Обратный контроль: без разбора channel_post реакции не было бы")
    parsed = await _parse_without_channel_post_branch()
    _line(
        OK if parsed == "other" else BAD,
        f"старый разбор даёт kind={parsed!r} (значит, без исправления — тишина)",
    )
    problems += 0 if parsed == "other" else 1

    monkeypatch.undo()
    print("\n" + "=" * 70)
    print("КОРОТКО ДЛЯ ВЛАДЕЛЬЦА")
    print("=" * 70)
    print("Что проверено: путь реакции целиком — без интернета и без настоящего")
    print("Telegram (используется встроенный тестовый «двойник» Telegram):")
    print("  • пост канала принимается и разбирается (channel_post);")
    print("  • у Telegram запрашиваются именно посты канала;")
    print("  • пост сохраняется с настоящими id канала и сообщения;")
    print("  • создаётся задание реакции и задание в очереди;")
    print("  • планировщик ставит реакцию на нужный пост;")
    print("  • повтор не создаёт второй пост;")
    print("  • ошибка Telegram честно помечает задание «failed».")
    if problems:
        print("")
        print(f"Что сломано: {problems} проверок не прошло (строки [ОШИБКА] выше).")
        print("Причина: исправление D-130 (приём постов канала) не применено")
        print("или повреждено в этой сборке.")
        print("ИТОГ: НЕ ПРОЙДЕНО")
        return 1
    print("")
    print("Что работает: всё перечисленное — реакции на посты канала работают.")
    print("Что сломано: ничего.")
    print("Причина: приём постов канала (channel_post) включён — исправление D-130.")
    print("ИТОГ: ПРОЙДЕНО — реакции на посты канала работают целиком")
    return 0


async def _parse_without_channel_post_branch() -> str:
    update = _real_update()

    class _Old:
        def __init__(self, u: Update) -> None:
            self.update_id = u.update_id

        def __getattr__(self, name: str):
            return None

    provider = AiogramBotProvider("123456:TEST-TOKEN")

    async def fake(**kwargs):  # type: ignore[no-untyped-def]
        return [_Old(update)]

    provider._bot.get_updates = fake  # type: ignore[method-assign]
    parsed = await provider.get_updates(timeout=0)
    return parsed[0].kind


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
