"""Analytics service (PHASE 8).

Turns raw counters into understandable insight. The service is read-only and has
no Telegram/FastAPI imports: it aggregates what the suite already stores and adds
plain-language summaries ("что это значит") so the Web UI can explain numbers
rather than just display them.

Three views compose the same repository:

* ``content()``  — posts over time, category mix, classification source, status.
* ``reactions()`` — reaction activity, success rate, emoji and per-bot mix.
* ``audience()`` — audience growth, sources, source effectiveness, invites.

``overview()`` bundles a compact version of all three plus the headline summary
used by the Dashboard. Nothing here exposes secrets or per-person PII — only
aggregate counts (D-010/D-029).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.invite import InviteStatus
from backend.app.db.models.reaction import ReactionJobStatus
from backend.app.db.repositories.analytics import AnalyticsRepository

#: Categories we explain by name; unknown ones fall back to the raw key.
_CATEGORY_TITLES = {
    "donation": "Донат / поддержка",
    "news": "Новости",
    "funny": "Смешное",
    "sad": "Грустное",
    "angry": "Гневное",
    "cute": "Милое",
    "support": "Поддержка",
    "announcement": "Объявления",
    "neutral": "Обычное",
    "unknown": "Без категории",
}

_SOURCE_TITLES = {
    "rules": "Обычные правила",
    "llm": "Мини-ИИ",
    "manual": "Вручную",
    "fallback": "Запасной вариант",
    "default": "По умолчанию",
    "unknown": "Не определено",
}

_AUDIENCE_STATUS_TITLES = {
    "active": "Активные",
    "inactive": "Неактивные",
    "deleted": "Удалённые",
    "blocked": "Заблокированные",
    "unknown": "Неизвестные",
}


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AnalyticsRepository(session)

    # ==================================================================
    # Content
    # ==================================================================
    async def content(self, *, days: int = 30, channel_id: str | None = None) -> dict[str, Any]:
        days = _clamp_days(days)
        total = await self.repo.posts_total(channel_id)
        per_day = await self.repo.posts_per_day(days, channel_id)
        by_category = await self.repo.posts_by_category(channel_id)
        by_source = await self.repo.posts_by_source(channel_id)
        by_status = await self.repo.posts_by_status(channel_id)

        window_total = sum(int(point["count"]) for point in per_day)
        previous_total = await self._posts_previous_window(days, window_total, channel_id)
        change = _percent_change(window_total, previous_total)

        return {
            "days": days,
            "posts_total": total,
            "posts_window": window_total,
            "posts_previous_window": previous_total,
            "change_percent": change,
            "average_per_day": round(window_total / days, 2),
            "per_day": per_day,
            "by_category": _titled_counts(by_category, _CATEGORY_TITLES),
            "by_source": _titled_counts(by_source, _SOURCE_TITLES),
            "by_status": by_status,
            "summary": self._content_summary(total, window_total, change, by_category),
        }

    async def _posts_previous_window(
        self, days: int, current_total: int, channel_id: str | None = None
    ) -> int:
        now = datetime.now(UTC)
        start = now - timedelta(days=days * 2)
        # posts_since(start) counts both windows; subtract the current one.
        two_windows = await self.repo.posts_since(start, channel_id)
        return max(two_windows - current_total, 0)

    @staticmethod
    def _content_summary(
        total: int, window_total: int, change: float, by_category: dict[str, int]
    ) -> str:
        if total == 0:
            return "Постов пока нет. Как только посты начнут поступать, здесь появится статистика."
        top = _top_key(by_category)
        top_title = _CATEGORY_TITLES.get(top, top) if top else ""
        parts = [f"Всего постов: {total}."]
        if window_total:
            parts.append(f"За выбранный период: {window_total}.")
        if change is not None and abs(change) >= 1:
            direction = "больше" if change > 0 else "меньше"
            parts.append(f"Это на {abs(round(change))}% {direction}, чем за предыдущий период.")
        if top_title:
            parts.append(f"Чаще всего встречается категория «{top_title}».")
        return " ".join(parts)

    # ==================================================================
    # Reactions
    # ==================================================================
    async def reactions(self, *, days: int = 30, channel_id: str | None = None) -> dict[str, Any]:
        days = _clamp_days(days)
        total = await self.repo.reactions_total(channel_id)
        by_status = await self.repo.reactions_by_status(channel_id)
        per_day = await self.repo.reactions_per_day(days, channel_id)
        completed_per_day = await self.repo.reactions_completed_per_day(days, channel_id)
        by_emoji = await self.repo.reactions_by_emoji(channel_id=channel_id)
        by_category = await self.repo.reactions_by_category(channel_id)
        by_bot = await self.repo.reactions_by_bot(channel_id=channel_id)

        done = by_status.get(ReactionJobStatus.DONE.value, 0)
        failed = by_status.get(ReactionJobStatus.FAILED.value, 0)
        finished = done + failed
        success_rate = round(done / finished, 4) if finished else None

        return {
            "days": days,
            "reactions_total": total,
            "by_status": by_status,
            "success_rate": success_rate,
            "per_day": per_day,
            "completed_per_day": completed_per_day,
            "by_emoji": by_emoji,
            "by_category": _titled_counts(by_category, _CATEGORY_TITLES),
            "by_bot": by_bot,
            "summary": self._reactions_summary(total, done, failed, success_rate),
        }

    @staticmethod
    def _reactions_summary(total: int, done: int, failed: int, success_rate: float | None) -> str:
        if total == 0:
            return "Реакций пока не было. Они появятся после обработки первых постов."
        parts = [f"Всего запланировано реакций: {total}."]
        if done:
            parts.append(f"Успешно выполнено: {done}.")
        if failed:
            parts.append(f"Не удалось: {failed} — проверьте журнал ошибок.")
        if success_rate is not None:
            percent = round(success_rate * 100)
            if percent >= 95:
                parts.append("Это отличный результат: почти все реакции прошли.")
            elif percent >= 80:
                parts.append(
                    f"Успешность {percent}% — в целом нормально, но стоит посмотреть ошибки."
                )
            else:
                parts.append(
                    f"Успешность {percent}% — много неудач. Откройте «Логи», чтобы понять причину."
                )
        return " ".join(parts)

    # ==================================================================
    # Audience
    # ==================================================================
    async def audience(self, *, days: int = 30, channel_id: str | None = None) -> dict[str, Any]:
        days = _clamp_days(days)
        total = await self.repo.audience_total(channel_id)
        since = datetime.now(UTC) - timedelta(days=7)
        new_7d = await self.repo.audience_since(since, channel_id)
        per_day = await self.repo.audience_per_day(days, channel_id)
        by_status = await self.repo.audience_by_status(channel_id)
        sources_total = await self.repo.audience_sources_total(channel_id)
        links_total = await self.repo.audience_links_total(channel_id)
        top_sources = await self.repo.top_sources(channel_id=channel_id)
        effectiveness = await self.repo.source_effectiveness(channel_id=channel_id)
        invites = await self.repo.invite_totals(channel_id)

        return {
            "days": days,
            "audience_total": total,
            "new_7d": new_7d,
            "per_day": per_day,
            "by_status": _titled_counts(by_status, _AUDIENCE_STATUS_TITLES),
            "sources_total": sources_total,
            "links_total": links_total,
            "top_sources": top_sources,
            "source_effectiveness": effectiveness,
            "invites": invites,
            "summary": self._audience_summary(total, new_7d, sources_total, invites),
        }

    @staticmethod
    def _audience_summary(
        total: int, new_7d: int, sources_total: int, invites: dict[str, int]
    ) -> str:
        if total == 0:
            if sources_total == 0:
                return "Аудитория пока не собиралась. Добавьте источник в разделе «Аудитория»."
            return "Источники добавлены, но пользователи ещё не найдены. Запустите сканирование."
        parts = [f"В базе {total} уникальных пользователей."]
        if new_7d:
            parts.append(f"За последние 7 дней добавлено {new_7d}.")
        invited = invites.get(InviteStatus.INVITED.value, 0)
        if invited:
            parts.append(f"Приглашено в целевой канал: {invited}.")
        parts.append(f"Источников: {sources_total}.")
        return " ".join(parts)

    # ==================================================================
    # Overview (Dashboard)
    # ==================================================================
    async def overview(self, *, days: int = 30, channel_id: str | None = None) -> dict[str, Any]:
        content = await self.content(days=days, channel_id=channel_id)
        reactions = await self.reactions(days=days, channel_id=channel_id)
        audience = await self.audience(days=days, channel_id=channel_id)
        account_connected = await self.repo.account_connected()
        return {
            "days": days,
            "channel_id": channel_id or "",
            "generated_at": datetime.now(UTC),
            "account_connected": account_connected,
            "account_note": self._account_note(account_connected),
            "headline": {
                "posts_total": content["posts_total"],
                "posts_window": content["posts_window"],
                "posts_change_percent": content["change_percent"],
                "reactions_total": reactions["reactions_total"],
                "reaction_success_rate": reactions["success_rate"],
                "audience_total": audience["audience_total"],
                "audience_new_7d": audience["new_7d"],
                "sources_total": audience["sources_total"],
            },
            "content": content,
            "reactions": reactions,
            "audience": audience,
            "summary": self._overview_summary(content, reactions, audience),
        }

    @staticmethod
    def _account_note(account_connected: bool) -> str:
        """Explain what the numbers cover for the current connection type."""
        if account_connected:
            return ""
        return (
            "Аналитика работает без личного аккаунта: учтены посты, реакции и "
            "кампании после подключения ботов. Историческая информация недоступна "
            "этому типу подключения."
        )

    @staticmethod
    def _overview_summary(
        content: dict[str, Any], reactions: dict[str, Any], audience: dict[str, Any]
    ) -> list[str]:
        """A short list of plain-language takeaways for the Dashboard."""
        notes: list[str] = []
        notes.append(content["summary"])
        if content["posts_total"]:
            notes.append(reactions["summary"])
        notes.append(audience["summary"])
        if content["change_percent"] is not None and content["change_percent"] >= 25:
            notes.append(
                "Активность заметно выросла по сравнению с прошлым периодом — хороший момент "
                "посмотреть, какие категории постов работают лучше."
            )
        if reactions["success_rate"] is not None and reactions["success_rate"] < 0.8:
            notes.append(
                "Часть реакций не выполняется. Откройте «Логи» и раздел «Реакции», чтобы "
                "проверить ботов и лимиты."
            )
        return notes


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _clamp_days(days: int) -> int:
    try:
        value = int(days)
    except (TypeError, ValueError):
        value = 30
    return max(1, min(value, 365))


def _percent_change(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None if current <= 0 else 100.0
    return round((current - previous) / previous * 100, 1)


def _top_key(counts: dict[str, int]) -> str:
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: item[1])[0]


def _titled_counts(counts: dict[str, int], titles: dict[str, str]) -> list[dict[str, object]]:
    """Convert a ``{key: count}`` map into a titled, count-sorted list."""
    items = [
        {"key": key, "title": titles.get(key, key), "count": int(count)}
        for key, count in counts.items()
    ]
    items.sort(key=lambda item: item["count"], reverse=True)
    return items


__all__ = ["AnalyticsService"]
