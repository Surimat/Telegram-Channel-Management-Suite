"""Donor discovery service (v1.1: find, score and compare donor candidates).

This is the *discovery* counterpart to :class:`~backend.app.services.donor_service.DonorService`
(which analyses sources the owner already added). It:

* runs the configured :class:`DonorDiscoveryProvider` s (Telegram search, an
  optional web extension point, and manual entry);
* scores each candidate with an explainable suitability band (never an invented
  number — an exact "share of bots" is only reported when participant data
  exists);
* stores candidates as **proposals** (``donor_candidates``); the owner confirms
  before anything is added to ``audience_sources``;
* compares a chosen set of candidates side by side.

Nothing here searches for or downloads other people's sessions, registers bulk
accounts, or bypasses Telegram limits (D-006, D-065).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.models.audience import SourceType
from backend.app.db.models.donor_candidate import (
    FIT_CHECK,
    FIT_DOUBTFUL,
    FIT_SUITABLE,
    FIT_TITLES,
    FIT_UNKNOWN,
    SOURCE_MANUAL,
    SOURCE_TELEGRAM,
    SOURCE_TITLES,
    SOURCE_WEB,
    DonorCandidate,
)
from backend.app.db.repositories.proxies import DonorCandidateRepository
from backend.app.providers.discovery_base import (
    DiscoveredChannel,
    DiscoveryQuery,
    ManualDiscoveryProvider,
    WebDiscoveryProvider,
)
from backend.app.providers.telegram_discovery import TelegramDiscoveryProvider
from backend.app.services.events_service import EventsService

MODULE = "donor_discovery"

# --- Named thresholds (reviewable, not magic) --------------------------------
#: subscribers below which a channel looks too small to be a useful donor.
SMALL_SUBSCRIBERS = 300
#: subscribers at/above which a channel looks established.
LARGE_SUBSCRIBERS = 1000
#: reach ratio (avg_views / subscribers) considered healthy.
HEALTHY_REACH_RATIO = 0.15
#: reach ratio considered poor.
POOR_REACH_RATIO = 0.03

SIGNALS = {
    "large": "У канала много подписчиков.",
    "small": "Канал небольшой — аудитории может не хватить.",
    "healthy_reach": "Просмотры выглядят соразмерно подписчикам.",
    "poor_reach": "Просмотров мало относительно подписчиков.",
    "no_reach_data": "Охват недоступен — оценка по этому признаку не делалась.",
    "has_username": "У канала есть публичный @username.",
    "no_username": "Нет публичного @username — сложнее использовать как источник.",
}


@dataclass(slots=True)
class CandidateAssessment:
    fit: str
    fit_score: float
    confidence: str
    signals: list[str] = field(default_factory=list)
    explanations: list[str] = field(default_factory=list)
    summary: str = ""


def assess_candidate(candidate: DiscoveredChannel) -> CandidateAssessment:
    """Score one discovered candidate conservatively and explainably."""
    signals: list[str] = []
    score = 50.0

    if candidate.subscribers >= LARGE_SUBSCRIBERS:
        signals.append("large")
        score += 20.0
    elif candidate.subscribers and candidate.subscribers < SMALL_SUBSCRIBERS:
        signals.append("small")
        score -= 15.0

    if candidate.subscribers > 0 and candidate.avg_views > 0:
        ratio = candidate.avg_views / candidate.subscribers
        if ratio >= HEALTHY_REACH_RATIO:
            signals.append("healthy_reach")
            score += 20.0
        elif ratio < POOR_REACH_RATIO:
            signals.append("poor_reach")
            score -= 20.0
    else:
        signals.append("no_reach_data")

    if candidate.username:
        signals.append("has_username")
        score += 5.0
    else:
        signals.append("no_username")
        score -= 10.0

    score = max(0.0, min(100.0, score))
    fit = _fit(score, candidate)
    confidence = _confidence(candidate)
    return CandidateAssessment(
        fit=fit,
        fit_score=round(score, 1),
        confidence=confidence,
        signals=signals,
        explanations=[SIGNALS[s] for s in signals if s in SIGNALS],
        summary=_summary(fit, score, candidate, confidence),
    )


def _fit(score: float, candidate: DiscoveredChannel) -> str:
    if not candidate.username and not candidate.subscribers:
        return FIT_UNKNOWN
    if score >= 70:
        return FIT_SUITABLE
    if score >= 45:
        return FIT_CHECK
    return FIT_DOUBTFUL


def _confidence(candidate: DiscoveredChannel) -> str:
    if candidate.subscribers > 0 and candidate.avg_views > 0:
        return "medium"
    if candidate.subscribers > 0 or candidate.username:
        return "low"
    return "low"


def _summary(
    fit: str, score: float, candidate: DiscoveredChannel, confidence: str
) -> str:
    title = FIT_TITLES.get(fit, fit)
    parts = [f"Оценка: {title} ({round(score)}/100)."]
    if candidate.subscribers:
        parts.append(f"Подписчиков: ~{candidate.subscribers}.")
    else:
        parts.append("Число подписчиков неизвестно.")
    conf = {"low": "низкая", "medium": "средняя", "high": "высокая"}.get(confidence, confidence)
    parts.append(f"Уверенность: {conf}.")
    if fit == FIT_UNKNOWN:
        parts.append("Недостаточно данных для вывода — проверьте вручную.")
    return " ".join(parts)


class DonorDiscoveryService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        telegram_provider: TelegramDiscoveryProvider | None = None,
        web_provider: WebDiscoveryProvider | None = None,
        session_provider_factory: object | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.repo = DonorCandidateRepository(session)
        self.events = EventsService(session)
        self._session_provider_factory = session_provider_factory
        self._settings = settings or get_settings()
        self.telegram = telegram_provider or TelegramDiscoveryProvider(None)
        self.web = web_provider or WebDiscoveryProvider()
        self.manual = ManualDiscoveryProvider()

    async def _ensure_telegram(self, account_id: str | None) -> None:
        """Attach a Telegram provider backed by a connected account, if any.

        Prefers ``account_id`` when given; otherwise the first online, enabled
        account. When no account is available the provider stays unavailable and
        discovery reports that honestly.
        """
        if self.telegram.available or self._session_provider_factory is None:
            return
        from backend.app.db.models.session import SessionStatus
        from backend.app.services.session_service import SessionService

        service = SessionService(
            self.session,
            provider_factory=self._session_provider_factory,  # type: ignore[arg-type]
            settings=self._settings,
        )
        account = None
        if account_id:
            account = await service.get(account_id)
        if account is None:
            accounts = await service.list_accounts(status=SessionStatus.ONLINE, enabled=True)
            account = accounts[0] if accounts else None
        if account is None:
            return
        provider = await service.provider_for_with_proxy(account)
        self.telegram = TelegramDiscoveryProvider(provider)

    # --- inventory -----------------------------------------------------------
    async def list_candidates(self) -> list[DonorCandidate]:
        return await self.repo.list_all()

    async def get(self, candidate_id: str) -> DonorCandidate | None:
        return await self.repo.get(candidate_id)

    async def clear(self, *, provider: str | None = None) -> int:
        count = await self.repo.clear(provider=provider)
        await self.session.commit()
        return count

    # --- providers -----------------------------------------------------------
    def provider_status(self) -> list[dict[str, object]]:
        """Availability of each discovery provider (shown in the UI)."""
        return [
            {
                "name": SOURCE_TELEGRAM,
                "title": SOURCE_TITLES[SOURCE_TELEGRAM],
                "available": self.telegram.available,
                "message": (
                    "Использует поиск Telegram через подключённый аккаунт."
                    if self.telegram.available
                    else "Подключите аккаунт Telegram, чтобы искать каналы."
                ),
            },
            {
                "name": SOURCE_WEB,
                "title": SOURCE_TITLES[SOURCE_WEB],
                "available": self.web.available,
                "message": (
                    "Дополнительный источник (расширение)."
                    if self.web.available
                    else "Веб-поиск не настроен — это необязательно."
                ),
            },
            {
                "name": SOURCE_MANUAL,
                "title": SOURCE_TITLES[SOURCE_MANUAL],
                "available": True,
                "message": "Всегда доступен: введите @username или ссылку.",
            },
        ]

    async def discover(
        self,
        query: DiscoveryQuery,
        *,
        providers: list[str] | None = None,
        account_id: str | None = None,
    ) -> dict[str, object]:
        """Run discovery across the requested providers and store candidates.

        Returns a per-provider report; nothing is added to audience sources here.
        """
        chosen = providers or [SOURCE_TELEGRAM]
        if SOURCE_TELEGRAM in chosen:
            await self._ensure_telegram(account_id)
        reports: list[dict[str, object]] = []
        stored = 0

        for provider_name, provider in (
            (SOURCE_TELEGRAM, self.telegram),
            (SOURCE_WEB, self.web),
            (SOURCE_MANUAL, self.manual),
        ):
            if provider_name not in chosen:
                continue
            result = await provider.discover(query)
            stored += await self._store(result.candidates, query, provider_name)
            reports.append(
                _report(
                    result.provider,
                    result.ok,
                    result.message,
                    result.how_to_fix,
                    len(result.candidates),
                )
            )

        await self.session.commit()
        return {
            "query": query.text(),
            "providers": reports,
            "stored": stored,
            "candidates": [candidate_to_dict(c) for c in await self.list_candidates()],
        }

    async def _store(
        self, candidates: list[DiscoveredChannel], query: DiscoveryQuery, provider: str
    ) -> int:
        count = 0
        for cand in candidates:
            if not cand.username and cand.telegram_id is None:
                continue
            existing = await self.repo.find(cand.username) if cand.username else None
            assessment = assess_candidate(cand)
            if existing is None:
                existing = DonorCandidate(username=cand.username)
                await self.repo.add(existing)
            existing.provider = provider
            existing.query = query.text()[:255]
            existing.title = cand.title or cand.username
            existing.telegram_id = cand.telegram_id
            existing.kind = cand.kind or "channel"
            existing.subscribers = cand.subscribers
            existing.avg_views = cand.avg_views
            existing.activity = cand.activity
            existing.language = cand.language
            existing.fit = assessment.fit
            existing.fit_score = assessment.fit_score
            existing.confidence = assessment.confidence
            existing.signals = json.dumps(assessment.signals, ensure_ascii=False)
            existing.explanations = json.dumps(assessment.explanations, ensure_ascii=False)
            existing.summary = assessment.summary
            count += 1
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Поиск доноров: сохранено кандидатов — {count}.",
            explanation="Кандидаты не добавляются в источники автоматически.",
            operation="discover",
            status="ok",
        )
        return count

    # --- add to sources (explicit confirmation) ------------------------------
    async def add_to_sources(self, candidate_id: str) -> DonorCandidate:
        """Add a candidate to audience sources (the owner's explicit action)."""
        from backend.app.services.audience_service import AudienceService

        candidate = await self.repo.get(candidate_id)
        if candidate is None:
            raise ValueError("Кандидат не найден.")
        if candidate.added and candidate.added_source_id:
            return candidate
        reference = candidate.username or str(candidate.telegram_id or "")
        source = await AudienceService(self.session).add_source(
            reference=reference,
            title=candidate.title,
            source_type=SourceType.CHANNEL if candidate.kind == "channel" else SourceType.GROUP,
        )
        candidate.added = True
        candidate.added_source_id = source.id
        await self.session.flush()
        await self.session.commit()
        return candidate

    # --- comparison ----------------------------------------------------------
    async def compare(self, candidate_ids: list[str]) -> dict[str, object]:
        """Compare 2–10 candidates and name the best one with reasons."""
        if not (2 <= len(candidate_ids) <= 10):
            raise ValueError("Для сравнения выберите от 2 до 10 кандидатов.")
        rows: list[DonorCandidate] = []
        for cid in candidate_ids:
            row = await self.repo.get(cid)
            if row is not None:
                rows.append(row)
        if len(rows) < 2:
            raise ValueError("Нужно минимум два существующих кандидата.")
        ordered = sorted(rows, key=lambda r: r.fit_score, reverse=True)
        best = ordered[0]
        return {
            "items": [candidate_to_dict(r) for r in rows],
            "best_id": best.id,
            "best_title": best.title or best.username,
            "best_reason": _best_reason(best),
        }


def _best_reason(candidate: DonorCandidate) -> str:
    reasons: list[str] = []
    if candidate.subscribers:
        reasons.append(f"подписчиков ~{candidate.subscribers}")
    signals = _load(candidate.signals)
    if "healthy_reach" in signals:
        reasons.append("просмотры соразмерны подписчикам")
    if "poor_reach" in signals:
        reasons.append("но охват слабый")
    if candidate.username:
        reasons.append("есть публичный @username")
    base = f"Лучший кандидат: {candidate.title or candidate.username}"
    if reasons:
        base += " (" + ", ".join(reasons) + ")"
    base += f". Оценка {round(candidate.fit_score)}/100."
    return base


def _report(
    provider: str, ok: bool, message: str, how_to_fix: str, found: int
) -> dict[str, object]:
    return {
        "provider": provider,
        "title": SOURCE_TITLES.get(provider, provider),
        "ok": ok,
        "message": message,
        "how_to_fix": how_to_fix,
        "found": found,
    }


def _load(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def candidate_to_dict(row: DonorCandidate) -> dict[str, object]:
    """Serialise a candidate for the API (no secrets, no PII)."""
    return {
        "id": row.id,
        "query": row.query,
        "provider": row.provider,
        "provider_title": SOURCE_TITLES.get(row.provider, row.provider),
        "username": row.username,
        "title": row.title,
        "telegram_id": row.telegram_id,
        "kind": row.kind,
        "subscribers": row.subscribers,
        "avg_views": row.avg_views,
        "activity": row.activity,
        "language": row.language,
        "fit": row.fit,
        "fit_title": FIT_TITLES.get(row.fit, row.fit),
        "fit_score": row.fit_score,
        "confidence": row.confidence,
        "signals": _load(row.signals),
        "explanations": _load(row.explanations),
        "summary": row.summary,
        "added": row.added,
        "added_source_id": row.added_source_id,
    }


__all__ = [
    "MODULE",
    "SIGNALS",
    "CandidateAssessment",
    "DonorDiscoveryService",
    "assess_candidate",
    "candidate_to_dict",
]
