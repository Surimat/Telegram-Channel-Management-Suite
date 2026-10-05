"""Telegram-account donor discovery (v1.1).

Thin adapter that uses the existing :class:`~backend.app.providers.session_base.SessionProvider`
abstraction to run an **official** Telegram public search. It never imports
Telethon directly (that stays in ``telethon_session``), and it never bypasses a
Telegram limit: a FloodWait/privacy/authorization error becomes a friendly
provider error which the service surfaces as a discovery status.
"""

from __future__ import annotations

from backend.app.providers.discovery_base import (
    DiscoveredChannel,
    DiscoveryQuery,
    DiscoveryResult,
)
from backend.app.providers.errors import TelegramProviderError
from backend.app.providers.session_base import SessionProvider

NAME = "telegram"


class TelegramDiscoveryProvider:
    """Discover public channels through a connected user account."""

    def __init__(self, session_provider: SessionProvider | None) -> None:
        self._provider = session_provider

    @property
    def name(self) -> str:
        return NAME

    @property
    def available(self) -> bool:
        return self._provider is not None

    async def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        if self._provider is None:
            return DiscoveryResult(
                provider=self.name,
                ok=False,
                available=False,
                message="Поиск Telegram недоступен без подключённого аккаунта.",
                how_to_fix=(
                    "Подключите свой аккаунт Telegram в разделе «Аккаунты» или "
                    "используйте ручной ввод."
                ),
            )
        text = query.text()
        if not text and not query.seed_channel:
            return DiscoveryResult(
                provider=self.name,
                ok=False,
                message="Укажите тему или ключевые слова.",
                how_to_fix="Например: «новости», «криптовалюта», «спорт».",
            )
        refs: list[object] = []
        notes: list[str] = []
        if text:
            try:
                refs.extend(await self._provider.search_public(text, limit=50))
            except TelegramProviderError as exc:
                return DiscoveryResult(
                    provider=self.name,
                    ok=False,
                    message=exc.message,
                    how_to_fix=exc.how_to_fix,
                )
        if query.seed_channel:
            try:
                recs = await self._provider.get_channel_recommendations(
                    query.seed_channel, limit=50
                )
                refs.extend(recs)
                if recs:
                    notes.append("Добавлены официальные рекомендации Telegram.")
            except TelegramProviderError as exc:
                # A failed recommendations call must not sink a successful search.
                notes.append(f"Рекомендации недоступны: {exc.message}")
        candidates = _dedupe([self._to_candidate(ref) for ref in refs])
        candidates = _apply_filters(candidates, query)
        message = (
            f"Найдено кандидатов: {len(candidates)}."
            if candidates
            else "Telegram не вернул подходящих публичных каналов."
        )
        if notes:
            message = f"{message} {' '.join(notes)}"
        return DiscoveryResult(
            provider=self.name,
            ok=True,
            candidates=candidates,
            message=message,
        )

    @staticmethod
    def _to_candidate(ref: object) -> DiscoveredChannel:
        return DiscoveredChannel(
            username=getattr(ref, "username", "") or "",
            title=getattr(ref, "title", "") or "",
            telegram_id=getattr(ref, "id", None),
            kind=getattr(ref, "kind", "channel") or "channel",
            subscribers=int(getattr(ref, "subscribers", 0) or 0),
            avg_views=float(getattr(ref, "avg_views", 0.0) or 0.0),
            language=getattr(ref, "language", "") or "",
            provider=NAME,
        )


def _dedupe(candidates: list[DiscoveredChannel]) -> list[DiscoveredChannel]:
    """Drop duplicate channels by username/id, keeping the first occurrence."""
    seen: set[str] = set()
    result: list[DiscoveredChannel] = []
    for c in candidates:
        key = c.username.lower() if c.username else f"id:{c.telegram_id}"
        if key in seen:
            continue
        seen.add(key)
        result.append(c)
    return result


def _apply_filters(
    candidates: list[DiscoveredChannel], query: DiscoveryQuery
) -> list[DiscoveredChannel]:
    """Filter candidates by the query's explicit numeric constraints only.

    Size/language filters are applied only when the value is known, so a channel
    whose subscriber count Telegram hid is not silently dropped.
    """
    result: list[DiscoveredChannel] = []
    for c in candidates:
        if query.min_subscribers and c.subscribers and c.subscribers < query.min_subscribers:
            continue
        if query.max_subscribers and c.subscribers and c.subscribers > query.max_subscribers:
            continue
        if query.language and c.language and c.language != query.language:
            continue
        result.append(c)
    return result


__all__ = ["NAME", "TelegramDiscoveryProvider"]
