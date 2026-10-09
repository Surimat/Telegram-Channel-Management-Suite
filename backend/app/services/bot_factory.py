"""Bot Factory service (v1.3: prepare managed bots in bulk).

The owner says "I need 20 managed bots". This service:

1. generates readable display names and Telegram-valid usernames from a small
   template set;
2. checks username availability with the **official** ``bots.checkUsername``
   method (never a local guess — a local check is only a pre-filter), debounced
   and concurrency-limited so it never floods Telegram;
3. creates the bots through the **official** managed-bot flow (``bots.createBot``
   with a manager bot, or the ``t.me/newbot`` deep link when no user account is
   connected);
4. registers each created bot in the Bot inventory and, via the manager bot,
   fetches its token (sealed at rest — the token is never shown);
5. can bind the created bots to a registry channel and verify the real rights.

Nothing here bypasses Telegram's ownership limit, FloodWait or privacy checks
(D-006). The limit note is shown verbatim in the UI (never promise unlimited
bots). The suite never searches for or imports someone else's bots.
"""

from __future__ import annotations

import asyncio
import contextlib
import re

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.models.bot_factory import (
    BATCH_STATUS_TITLES,
    BOT_CREATE_LIMIT_NOTE,
    CANDIDATE_STATUS_TITLES,
    QUEUE_STATE_TITLES,
    BatchStatus,
    BotBatch,
    BotCandidate,
    CandidateStatus,
    QueueState,
)
from backend.app.db.repositories.bot_factory import (
    BotBatchRepository,
    BotCandidateRepository,
)
from backend.app.db.repositories.bots import BotRepository
from backend.app.providers.errors import TelegramProviderError
from backend.app.services.binding_service import BindingService
from backend.app.services.bot_service import BotService, BotServiceError
from backend.app.services.events_service import EventsService
from backend.app.services.session_service import SessionProviderFactory, SessionService

MODULE = "bot_factory"

#: Durable-queue kind for a bot-creation operation (v1.7). The handler runs one
#: bounded pass over the batch's queued candidates, so a restart resumes the
#: queue instead of losing it (D-008 style).
BOT_FACTORY_JOB_KIND = "bot_factory.create"

#: Local username rules (a pre-filter only; Telegram is the source of truth).
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,29}bot$")
#: Telegram recommends debouncing ``bots.checkUsername`` by 200 ms.
CHECK_DEBOUNCE_SECONDS = 0.2
#: How many availability checks may run at once (kept small on purpose).
CHECK_CONCURRENCY = 2
#: Maximum bots per batch (Telegram caps ownership well below this anyway).
MAX_BATCH_SIZE = 50

#: Queue sizes the UI offers (v1.7). 10/20/50, bounded by MAX_BATCH_SIZE.
QUEUE_SIZES = (10, 20, 50)


def mask_token(token: str) -> str:
    """Return a masked, display-safe form of a bot token.

    The token itself is a secret (D-110): it is never shown, logged or exported.
    Only a short, non-reversible shape is exposed so the owner can tell *which*
    credential is stored. ``123456789:AAH...xyz`` → ``1234…xyz``.
    """
    value = (token or "").strip()
    if not value:
        return ""
    bot_id = value.split(":", 1)[0]
    tail = value[-4:] if len(value) > 4 else ""
    head = bot_id[:4] if bot_id else value[:2]
    return f"{head}…{tail}"

NAME_TEMPLATES = {
    "index": "{prefix} {index}",
    "helper": "{prefix} Helper {index}",
    "media": "{prefix} Media {index}",
    "bot": "{prefix} Bot {index}",
}

USERNAME_TEMPLATES = {
    "index": "{prefix}_{index}_bot",
    "helper": "{prefix}_helper_{index}_bot",
    "media": "{prefix}_media_{index}_bot",
    "bot": "{prefix}_bot_{index}_bot",
}

STYLE_TITLES = {
    "neutral": "нейтральный",
    "friendly": "дружелюбный",
    "official": "официальный",
}


class BotFactoryError(Exception):
    """A bot-factory operation failed; carries a friendly message and a hint."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Pure generators / validators
# ---------------------------------------------------------------------------
def sanitize_prefix(prefix: str) -> str:
    """Keep only characters Telegram allows in a username fragment."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", (prefix or "").strip())
    return cleaned


def generate_name(
    template: str, prefix: str, index: int, *, topic: str = "", style: str = "neutral"
) -> str:
    """Build a readable display name (1–64 chars, never long/strange)."""
    tpl = template or NAME_TEMPLATES["index"]
    base = sanitize_prefix(prefix) or "Bot"
    name = tpl.format(prefix=base, index=index, topic=(topic or "").strip())
    # Friendly/official styles nudge the display name, never the username.
    if style == "friendly" and not name.endswith(")"):
        name = f"{name}"
    name = re.sub(r"\s+", " ", name).strip()
    return name[:64]


def generate_username(template: str, prefix: str, index: int) -> str:
    """Build a candidate username that satisfies the local Telegram rules."""
    tpl = template or USERNAME_TEMPLATES["index"]
    base = sanitize_prefix(prefix) or "bot"
    raw = tpl.format(prefix=base, index=index).lower()
    raw = re.sub(r"[^a-z0-9_]", "", raw)
    if not raw.endswith("bot"):
        raw += "bot"
    if len(raw) > 32:
        raw = raw[:29] + "bot"
    return raw


def validate_username(username: str) -> tuple[bool, str]:
    """Local pre-check only. Never proof of availability (Telegram decides)."""
    value = (username or "").strip()
    if not value:
        return False, "Пустое имя пользователя."
    if len(value) < 5:
        return False, "Слишком короткое имя (минимум 5 символов с учётом «bot»)."
    if len(value) > 32:
        return False, "Слишком длинное имя (максимум 32 символа)."
    if not value.endswith("bot"):
        return False, "Имя должно заканчиваться на «bot»."
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        return False, "Допустимы только латинские буквы, цифры и подчёркивание."
    if not value[0].isalpha():
        return False, "Имя должно начинаться с буквы."
    return True, ""


def manager_deep_link(manager_username: str, username: str, name: str = "") -> str:
    """Official ``t.me/newbot/<manager>/<username>`` managed-bot creation link."""
    manager = (manager_username or "").lstrip("@")
    if not manager:
        return ""
    query = f"?name={name}" if name else ""
    return f"https://t.me/newbot/{manager}/{username}{query}"


def _is_available_status(value: object) -> bool:
    return str(getattr(value, "value", value)) == CandidateStatus.AVAILABLE.value


def _is_create_ready(value: object, *, via_deeplink: bool) -> bool:
    """Which candidates may be created in this mode.

    Native creation only touches candidates Telegram confirmed as available;
    deep-link mode may also offer not-yet-checked (``generated``) candidates,
    since the owner creates them by hand in Telegram.
    """
    status = str(getattr(value, "value", value))
    if status in (CandidateStatus.AVAILABLE.value, CandidateStatus.READY.value):
        return True
    return via_deeplink and status == CandidateStatus.GENERATED.value


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class BotFactoryService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        session_provider_factory: SessionProviderFactory | None = None,
        bot_service: BotService | None = None,
        binding_service: BindingService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.batches = BotBatchRepository(session)
        self.candidates = BotCandidateRepository(session)
        self.bots = BotRepository(session)
        self.events = EventsService(session)
        self._session_factory = session_provider_factory
        self._bots_override = bot_service
        self._binding_service = binding_service

    def _bot_service(self) -> BotService:
        if self._bots_override is not None:
            return self._bots_override
        return BotService(self.session)

    def _binding_service(self) -> BindingService:
        if self._binding_service is not None:
            return self._binding_service
        return BindingService(self.session)

    async def _session_provider(self, account_id: str = ""):  # type: ignore[no-untyped-def]
        if self._session_factory is None:
            return None
        service = SessionService(self.session, provider_factory=self._session_factory)
        account = await service.get(account_id) if account_id else None
        if account is None:
            accounts = await service.list_accounts(enabled=True)
            account = accounts[0] if accounts else None
        if account is None:
            return None
        return await service.provider_for_with_proxy(account)

    async def _manager_username(self, manager_bot_id: str) -> str:
        if manager_bot_id:
            bot = await self.bots.get(manager_bot_id)
            if bot is not None and bot.username:
                return bot.username
        manager = await self.bots.get_manager()
        return manager.username if manager is not None else ""

    # --- batches -------------------------------------------------------------
    async def create_batch(
        self,
        *,
        title: str = "",
        prefix: str = "",
        topic: str = "",
        style: str = "neutral",
        count: int = 0,
        name_template: str = "",
        username_template: str = "",
        manager_bot_id: str = "",
        account_id: str = "",
        channel_id: str = "",
    ) -> BotBatch:
        """Generate a batch of bot candidates (names + usernames, unchecked)."""
        count = int(count or 0)
        if count < 1:
            raise BotFactoryError(
                "Укажите количество ботов.",
                how_to_fix=f"Например, 20. Максимум за пакет — {MAX_BATCH_SIZE}.",
            )
        if count > MAX_BATCH_SIZE:
            raise BotFactoryError(
                f"За один пакет можно подготовить не больше {MAX_BATCH_SIZE} ботов.",
                how_to_fix=BOT_CREATE_LIMIT_NOTE,
            )
        prefix = sanitize_prefix(prefix)
        if not prefix:
            raise BotFactoryError(
                "Укажите префикс (латинские буквы, цифры, подчёркивание).",
                how_to_fix="Например: MixMedia.",
            )
        name_tpl = name_template or NAME_TEMPLATES.get(style, NAME_TEMPLATES["index"])
        user_tpl = username_template or USERNAME_TEMPLATES["index"]
        manager_username = await self._manager_username(manager_bot_id)

        batch = BotBatch(
            title=title or f"{prefix} Bots",
            prefix=prefix,
            topic=topic,
            style=style,
            name_template=name_tpl,
            username_template=user_tpl,
            manager_bot_id=manager_bot_id,
            manager_username=manager_username,
            account_id=account_id,
            channel_id=channel_id,
            requested_count=count,
            status=BatchStatus.DRAFT,
            note=BOT_CREATE_LIMIT_NOTE,
        )
        await self.batches.add(batch)
        rows: list[BotCandidate] = []
        for index in range(1, count + 1):
            name = generate_name(name_tpl, prefix, index, topic=topic, style=style)
            username = generate_username(user_tpl, prefix, index)
            ok, reason = validate_username(username)
            rows.append(
                BotCandidate(
                    batch_id=batch.id,
                    index=index,
                    suggested_name=name,
                    suggested_username=username,
                    username_status="unknown",
                    username_message="" if ok else reason,
                    creation_status=(
                        CandidateStatus.GENERATED if ok else CandidateStatus.INVALID
                    ),
                    queue_state=(
                        QueueState.PENDING.value
                        if ok
                        else QueueState.FAILED.value
                    ),
                    deep_link=manager_deep_link(manager_username, username, name),
                )
            )
        await self.candidates.add_many(rows)
        await self.events.info(
            MODULE,
            f"Создан пакет ботов «{batch.title}»: {count}.",
            explanation="Проверьте доступность имён перед созданием.",
            operation="create_batch",
            status="ok",
        )
        await self.session.commit()
        return batch

    async def list_batches(
        self, *, limit: int = 100, offset: int = 0
    ) -> tuple[list[BotBatch], int]:
        return await self.batches.list_all(limit=limit, offset=offset)

    async def get_batch(self, batch_id: str) -> BotBatch:
        batch = await self.batches.get(batch_id)
        if batch is None:
            raise BotFactoryError("Пакет не найден.", status_code=404)
        return batch

    async def list_candidates(self, batch_id: str) -> list[BotCandidate]:
        return await self.candidates.list_for_batch(batch_id)

    async def delete_batch(self, batch_id: str) -> None:
        batch = await self.get_batch(batch_id)
        await self.candidates.delete_for_batch(batch_id)
        await self.batches.delete(batch)
        await self.session.commit()

    # --- availability --------------------------------------------------------
    async def check_availability(self, batch_id: str, *, account_id: str = "") -> BotBatch:
        """Check every candidate's username with Telegram (bounded + debounced)."""
        batch = await self.get_batch(batch_id)
        rows = await self.candidates.list_for_batch(batch_id)
        provider = await self._session_provider(account_id or batch.account_id)
        batch.status = BatchStatus.CHECKING
        await self.session.flush()

        if provider is None:
            # Without an account we cannot ask Telegram: leave statuses honest.
            batch.status = BatchStatus.READY
            await self.session.commit()
            raise BotFactoryError(
                "Для проверки имён нужен подключённый аккаунт Telegram.",
                how_to_fix="Добавьте аккаунт в разделе «Аккаунты» или создайте ботов по ссылкам.",
                status_code=409,
            )

        semaphore = asyncio.Semaphore(CHECK_CONCURRENCY)

        async def _check(row: BotCandidate) -> None:
            ok, reason = validate_username(row.suggested_username)
            if not ok:
                row.username_status = "invalid"
                row.username_message = reason
                row.creation_status = CandidateStatus.INVALID
                row.queue_state = QueueState.SKIPPED.value
                return
            async with semaphore:
                await asyncio.sleep(CHECK_DEBOUNCE_SECONDS)  # Telegram debounce
                try:
                    available = await provider.check_username(row.suggested_username)
                except TelegramProviderError as exc:
                    row.username_status = "error"
                    row.username_message = exc.message
                    row.creation_status = CandidateStatus.FAILED
                    row.error = exc.message
                    row.queue_state = QueueState.FAILED.value
                    return
            row.username_status = "available" if available else "occupied"
            row.username_message = (
                "Имя свободно." if available else "Имя занято."
            )
            row.creation_status = (
                CandidateStatus.AVAILABLE if available else CandidateStatus.OCCUPIED
            )
            # Confirmed-free usernames become the real creation queue; occupied or
            # invalid ones are skipped (their operation will never run).
            row.queue_state = (
                QueueState.QUEUED.value if available else QueueState.SKIPPED.value
            )

        try:
            await asyncio.gather(*(_check(row) for row in rows))
        finally:
            with contextlib.suppress(Exception):
                await provider.aclose()

        batch.status = BatchStatus.READY
        await self.events.info(
            MODULE,
            f"Проверка имён пакета «{batch.title}» завершена.",
            operation="check_availability",
            status="ok",
        )
        await self.session.commit()
        return batch

    async def regenerate_candidate(self, candidate_id: str) -> BotCandidate:
        """Re-generate one occupied/invalid candidate's username (index bumped)."""
        row = await self.candidates.get(candidate_id)
        if row is None:
            raise BotFactoryError("Кандидат не найден.", status_code=404)
        batch = await self.get_batch(row.batch_id)
        new_index = row.index + batch.requested_count
        row.index = new_index
        row.suggested_username = generate_username(batch.username_template, batch.prefix, new_index)
        row.suggested_name = generate_name(
            batch.name_template, batch.prefix, new_index, topic=batch.topic, style=batch.style
        )
        row.username_status = "unknown"
        row.username_message = ""
        row.creation_status = CandidateStatus.GENERATED
        row.error = ""
        row.deep_link = manager_deep_link(
            batch.manager_username, row.suggested_username, row.suggested_name
        )
        await self.session.commit()
        return row

    async def availability_summary(self, batch_id: str) -> dict[str, int]:
        rows = await self.candidates.list_for_batch(batch_id)
        counts = {
            "total": len(rows),
            "available": 0,
            "occupied": 0,
            "error": 0,
            "created": 0,
            "tokens": 0,
        }
        for row in rows:
            status = row.creation_status
            if status is CandidateStatus.AVAILABLE:
                counts["available"] += 1
            elif status is CandidateStatus.OCCUPIED:
                counts["occupied"] += 1
            elif status is CandidateStatus.FAILED:
                counts["error"] += 1
            if status in (CandidateStatus.CREATED, CandidateStatus.TOKEN_IMPORTED):
                counts["created"] += 1
            if status is CandidateStatus.TOKEN_IMPORTED:
                counts["tokens"] += 1
        return counts

    # --- creation ------------------------------------------------------------
    async def create_batch_bots(self, batch_id: str, *, via_deeplink: bool = False) -> BotBatch:
        """Create every available candidate through the official managed-bot flow.

        Native creation needs a connected user account (``bots.createBot``). When
        none is available the batch is left in deep-link mode: the owner opens
        each link and the bot is registered on return (``adopt_created``).
        """
        batch = await self.get_batch(batch_id)
        rows = await self.candidates.list_for_batch(batch_id)
        manager_username = batch.manager_username or await self._manager_username(
            batch.manager_bot_id
        )
        batch.manager_username = manager_username
        if not manager_username:
            raise BotFactoryError(
                "Не выбран управляющий бот.",
                how_to_fix="Добавьте управляющего бота в разделе «Боты».",
                status_code=409,
            )

        provider = None if via_deeplink else await self._session_provider(batch.account_id)
        if provider is None:
            # Deep-link mode: just refresh the links and mark the batch ready.
            for row in rows:
                if _is_create_ready(row.creation_status, via_deeplink=True):
                    row.deep_link = manager_deep_link(
                        manager_username, row.suggested_username, row.suggested_name
                    )
                    # Hand-created bots are queued until the owner confirms them.
                    if row.queue_state == QueueState.PENDING.value:
                        row.queue_state = QueueState.QUEUED.value
            batch.status = BatchStatus.READY
            await self.session.commit()
            return batch

        # Starting a native run revives the queue unless the owner cancelled it.
        batch.status = BatchStatus.CREATING
        batch.queue_cancelled = False
        await self.session.flush()
        created = 0
        failed = 0
        try:
            for row in rows:
                if not _is_create_ready(row.creation_status, via_deeplink=via_deeplink):
                    continue
                row.creation_status = CandidateStatus.CREATING
                row.queue_state = QueueState.RUNNING.value
                row.attempts += 1
                await self.session.flush()
                try:
                    ref = await provider.create_managed_bot(
                        row.suggested_name,
                        row.suggested_username,
                        manager_username,
                        via_deeplink=via_deeplink,
                    )
                except TelegramProviderError as exc:
                    row.creation_status = CandidateStatus.FAILED
                    row.queue_state = QueueState.FAILED.value
                    row.error = exc.message
                    failed += 1
                    continue
                row.telegram_id = ref.user_id
                row.creation_status = CandidateStatus.CREATED
                row.queue_state = QueueState.SUCCESS.value
                bot = await self._bot_service().register_managed_bot(
                    ref.user_id,
                    username=ref.username or row.suggested_username,
                    title=ref.first_name or row.suggested_name,
                )
                row.bot_id = bot.id
                created += 1
        finally:
            with contextlib.suppress(Exception):
                await provider.aclose()

        batch.created_count = created
        batch.failed_count = failed
        batch.status = BatchStatus.COMPLETED if failed == 0 else BatchStatus.READY
        if batch.status is BatchStatus.COMPLETED:
            from backend.app.db.base import utcnow

            batch.completed_at = utcnow()
        await self.events.info(
            MODULE,
            f"Создание ботов «{batch.title}»: создано {created}, ошибок {failed}.",
            operation="create_batch_bots",
            status="ok",
        )
        await self.session.commit()
        return batch

    async def adopt_created(
        self, batch_id: str, username: str, telegram_id: int, *, title: str = ""
    ) -> BotCandidate:
        """Register a bot the owner created via a deep link (manager update)."""
        batch = await self.get_batch(batch_id)
        rows = await self.candidates.list_for_batch(batch_id)
        row = next(
            (r for r in rows if r.suggested_username == username.lstrip("@")), None
        )
        if row is None:
            raise BotFactoryError("Кандидат с таким именем не найден.", status_code=404)
        bot = await self._bot_service().register_managed_bot(
            telegram_id, username=username.lstrip("@"), title=title or row.suggested_name
        )
        row.telegram_id = telegram_id
        row.bot_id = bot.id
        row.creation_status = CandidateStatus.CREATED
        batch.created_count += 1
        await self.session.commit()
        return row

    # --- token registration --------------------------------------------------
    async def register_tokens(self, batch_id: str) -> dict[str, int]:
        """Fetch tokens for created bots via the manager bot (sealed, never shown)."""
        await self.get_batch(batch_id)
        rows = await self.candidates.list_for_batch(batch_id)
        imported = 0
        pending = 0
        for row in rows:
            if row.creation_status is not CandidateStatus.CREATED or not row.bot_id:
                continue
            try:
                bot = await self._bot_service().fetch_managed_bot_token(row.bot_id)
            except BotServiceError as exc:
                row.error = exc.message
                pending += 1
                continue
            row.creation_status = CandidateStatus.TOKEN_IMPORTED
            row.queue_state = QueueState.SUCCESS.value
            # Show only a masked, non-reversible hint. The token itself stays
            # sealed in the Bot row and is never decrypted here, logged or
            # exported (D-110).
            ident = str(row.telegram_id or bot.telegram_id or "")
            if ident:
                row.token_mask = mask_token(ident)
            imported += 1
        await self.session.commit()
        return {"imported": imported, "pending": pending}

    # --- creation queue (v1.7) ----------------------------------------------
    async def enqueue_candidates(self, batch_id: str) -> BotBatch:
        """Queue every creatable candidate (the "start creation" action).

        A batch is a size-10/20/50 *queue* (D-109). Only candidates that Telegram
        confirmed free and the owner has not skipped are queued; the rest stay
        ``skipped``. Queuing does not create anything — the durable handler does.
        """
        batch = await self.get_batch(batch_id)
        rows = await self.candidates.list_for_batch(batch_id)
        queued = 0
        for row in rows:
            status = row.creation_status
            if status in (
                CandidateStatus.AVAILABLE,
                CandidateStatus.READY,
                CandidateStatus.GENERATED,
            ) and row.queue_state not in (
                QueueState.SUCCESS.value,
                QueueState.SKIPPED.value,
            ):
                row.queue_state = QueueState.QUEUED.value
                queued += 1
        batch.queue_cancelled = False
        if queued:
            batch.status = BatchStatus.READY
        await self.session.commit()
        return batch

    async def retry_candidate(self, candidate_id: str) -> BotCandidate:
        """Re-queue one failed operation (retry). A created bot is never re-made."""
        row = await self.candidates.get(candidate_id)
        if row is None:
            raise BotFactoryError("Кандидат не найден.", status_code=404)
        if row.creation_status in (
            CandidateStatus.CREATED,
            CandidateStatus.TOKEN_IMPORTED,
        ):
            raise BotFactoryError(
                "Этот бот уже создан — повтор не нужен.",
                how_to_fix="При необходимости получите токен.",
                status_code=409,
            )
        batch = await self.get_batch(row.batch_id)
        row.queue_state = QueueState.QUEUED.value
        row.creation_status = CandidateStatus.READY
        row.error = ""
        batch.queue_cancelled = False
        batch.status = BatchStatus.READY
        await self.session.commit()
        return row

    async def skip_candidate(self, candidate_id: str) -> BotCandidate:
        """Skip one operation; the rest of the queue continues."""
        row = await self.candidates.get(candidate_id)
        if row is None:
            raise BotFactoryError("Кандидат не найден.", status_code=404)
        batch = await self.get_batch(row.batch_id)
        row.queue_state = QueueState.SKIPPED.value
        row.creation_status = CandidateStatus.CANCELLED
        batch.skipped_count += 1
        await self.session.commit()
        return row

    async def cancel_queue(self, batch_id: str) -> BotBatch:
        """Cancel the queue. Created bots are kept; pending/failed ones stop."""
        batch = await self.get_batch(batch_id)
        rows = await self.candidates.list_for_batch(batch_id)
        for row in rows:
            if row.queue_state in (QueueState.QUEUED.value, QueueState.FAILED.value):
                row.queue_state = QueueState.CANCELLED.value
        batch.queue_cancelled = True
        batch.status = BatchStatus.CANCELLED
        await self.events.info(
            MODULE,
            f"Очередь создания «{batch.title}» отменена.",
            explanation="Уже созданные боты сохранены и не откатываются.",
            operation="cancel_queue",
            status="ok",
        )
        await self.session.commit()
        return batch

    async def resume_queue(self, batch_id: str) -> BotBatch:
        """Re-open a cancelled queue so the remaining operations run again."""
        batch = await self.get_batch(batch_id)
        rows = await self.candidates.list_for_batch(batch_id)
        revived = 0
        for row in rows:
            if row.queue_state == QueueState.CANCELLED.value:
                row.queue_state = QueueState.QUEUED.value
                row.error = ""
                revived += 1
        batch.queue_cancelled = False
        batch.status = BatchStatus.READY if revived else batch.status
        await self.session.commit()
        return batch

    async def queue_progress(self, batch_id: str) -> dict[str, int]:
        """Counts for the progress view (queue_size/total/succeeded/failed/…)."""
        counts = await self.candidates.count_by_queue_state(batch_id)
        return {
            "total": sum(counts.values()),
            "pending": counts.get(QueueState.PENDING.value, 0),
            "queued": counts.get(QueueState.QUEUED.value, 0),
            "running": counts.get(QueueState.RUNNING.value, 0),
            "success": counts.get(QueueState.SUCCESS.value, 0),
            "failed": counts.get(QueueState.FAILED.value, 0),
            "skipped": counts.get(QueueState.SKIPPED.value, 0),
            "cancelled": counts.get(QueueState.CANCELLED.value, 0),
        }

    async def run_queue_once(self, batch_id: str, *, via_deeplink: bool = False) -> BotBatch:
        """One bounded queue pass — the durable job handler body (v1.7).

        Processes the next queued candidate only, so the scheduler ticks through
        the queue (restart-safe) instead of blocking on one long request. A
        cancelled or fully-drained queue is a no-op. Each operation is isolated:
        one failure never aborts the others.
        """
        batch = await self.get_batch(batch_id)
        if batch.queue_cancelled:
            return batch
        rows = await self.candidates.list_for_batch(batch_id)
        row = next(
            (r for r in rows if r.queue_state == QueueState.QUEUED.value), None
        )
        if row is None:
            # Nothing left to do: settle the batch status.
            if rows and all(
                r.queue_state
                in (
                    QueueState.SUCCESS.value,
                    QueueState.SKIPPED.value,
                    QueueState.CANCELLED.value,
                )
                for r in rows
            ):
                from backend.app.db.base import utcnow

                batch.status = BatchStatus.COMPLETED
                batch.completed_at = utcnow()
                await self.session.commit()
            return batch

        manager_username = batch.manager_username or await self._manager_username(
            batch.manager_bot_id
        )
        provider = None if via_deeplink else await self._session_provider(batch.account_id)
        if provider is None:
            # Without an account the operation is handed to Telegram by link.
            row.deep_link = manager_deep_link(
                manager_username, row.suggested_username, row.suggested_name
            )
            row.queue_state = QueueState.QUEUED.value
            return batch

        batch.status = BatchStatus.CREATING
        if not manager_username:
            raise BotFactoryError(
                "Не выбран управляющий бот.",
                how_to_fix="Добавьте управляющего бота в разделе «Боты».",
                status_code=409,
            )
        row.creation_status = CandidateStatus.CREATING
        row.queue_state = QueueState.RUNNING.value
        row.attempts += 1
        await self.session.flush()
        try:
            ref = await provider.create_managed_bot(
                row.suggested_name,
                row.suggested_username,
                manager_username,
                via_deeplink=via_deeplink,
            )
        except TelegramProviderError as exc:
            row.creation_status = CandidateStatus.FAILED
            row.queue_state = QueueState.FAILED.value
            row.error = exc.message
        else:
            row.telegram_id = ref.user_id
            row.creation_status = CandidateStatus.CREATED
            row.queue_state = QueueState.SUCCESS.value
            bot = await self._bot_service().register_managed_bot(
                ref.user_id,
                username=ref.username or row.suggested_username,
                title=ref.first_name or row.suggested_name,
            )
            row.bot_id = bot.id
        finally:
            with contextlib.suppress(Exception):
                await provider.aclose()

        progress = await self.queue_progress(batch_id)
        batch.created_count = progress["success"]
        batch.failed_count = progress["failed"]
        await self.session.commit()
        return batch

    # --- channel binding -----------------------------------------------------
    async def bind_created(
        self, batch_id: str, channel_id: str, *, function: str = "reactions"
    ) -> list[dict[str, object]]:
        """Connect created bots to a channel and verify the real rights."""
        batch = await self.get_batch(batch_id)
        batch.channel_id = channel_id
        rows = await self.candidates.list_for_batch(batch_id)
        binding_service = self._binding_service()
        results: list[dict[str, object]] = []
        for row in rows:
            if not row.bot_id:
                continue
            binding = await binding_service.connect(row.bot_id, channel_id, function=function)
            check = await binding_service.check(binding.id)
            results.append(
                {
                    "candidate_id": row.id,
                    "bot_id": row.bot_id,
                    "username": row.suggested_username,
                    "binding_id": binding.id,
                    "status": str(getattr(check.status, "value", check.status)),
                    "status_label": check.status_label,
                }
            )
        await self.session.commit()
        return results

    async def bind_created_many(
        self,
        batch_id: str,
        channel_ids: list[str],
        *,
        function: str = "reactions",
    ) -> list[dict[str, object]]:
        """Connect every created bot to several channels in one action (v2.0).

        Reuses the existing single-channel binding path — it is a fan-out, not a
        second binding implementation. One channel failing never aborts the rest.
        """
        targets = [c for c in dict.fromkeys(channel_ids) if c]
        if not targets:
            raise BotFactoryError(
                "Не выбран ни один канал.",
                how_to_fix="Отметьте хотя бы один канал для подключения.",
            )
        results: list[dict[str, object]] = []
        for channel_id in targets:
            for row in await self.bind_created(batch_id, channel_id, function=function):
                row["channel_id"] = channel_id
                results.append(row)
        await self.session.commit()
        return results

    # --- dashboard -----------------------------------------------------------
    async def dashboard(self, batch_id: str) -> dict[str, object]:
        batch = await self.get_batch(batch_id)
        counts = await self.availability_summary(batch_id)
        return {
            "batch_id": batch.id,
            "title": batch.title,
            "status": str(batch.status.value),
            "status_label": BATCH_STATUS_TITLES.get(batch.status, str(batch.status)),
            "requested_count": batch.requested_count,
            "created_count": batch.created_count,
            "failed_count": batch.failed_count,
            "skipped_count": batch.skipped_count,
            "queue_cancelled": batch.queue_cancelled,
            "counts": counts,
            "queue": await self.queue_progress(batch_id),
            "manager_username": batch.manager_username,
            "channel_id": batch.channel_id,
            "limit_note": BOT_CREATE_LIMIT_NOTE,
        }

    def candidate_to_dict(self, row: BotCandidate) -> dict[str, object]:
        queue_state = str(row.queue_state)
        return {
            "id": row.id,
            "batch_id": row.batch_id,
            "index": row.index,
            "suggested_name": row.suggested_name,
            "suggested_username": row.suggested_username,
            "username_status": row.username_status,
            "username_message": row.username_message,
            "creation_status": str(row.creation_status.value),
            "creation_status_label": CANDIDATE_STATUS_TITLES.get(
                row.creation_status, str(row.creation_status)
            ),
            "queue_state": queue_state,
            "queue_state_label": QUEUE_STATE_TITLES.get(queue_state, queue_state),
            "attempts": row.attempts,
            "bot_id": row.bot_id,
            "telegram_id": row.telegram_id,
            # Masked, non-reversible shape only; the token itself is sealed (D-110).
            "token_mask": row.token_mask,
            "deep_link": row.deep_link,
            "error": row.error,
        }

    def batch_to_dict(self, batch: BotBatch) -> dict[str, object]:
        return {
            "id": batch.id,
            "title": batch.title,
            "prefix": batch.prefix,
            "topic": batch.topic,
            "style": batch.style,
            "requested_count": batch.requested_count,
            "created_count": batch.created_count,
            "failed_count": batch.failed_count,
            "skipped_count": batch.skipped_count,
            "status": str(batch.status.value),
            "status_label": BATCH_STATUS_TITLES.get(batch.status, str(batch.status)),
            "manager_username": batch.manager_username,
            "channel_id": batch.channel_id,
            "queue_cancelled": batch.queue_cancelled,
            "limit_note": BOT_CREATE_LIMIT_NOTE,
        }


__all__ = [
    "BOT_CREATE_LIMIT_NOTE",
    "CHECK_CONCURRENCY",
    "CHECK_DEBOUNCE_SECONDS",
    "MAX_BATCH_SIZE",
    "NAME_TEMPLATES",
    "USERNAME_TEMPLATES",
    "BotFactoryError",
    "BotFactoryService",
    "generate_name",
    "generate_username",
    "manager_deep_link",
    "sanitize_prefix",
    "validate_username",
]
