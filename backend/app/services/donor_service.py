"""Donor analytics service (product slice: source quality).

Turns the data the suite already stores about an audience source into an
explainable quality indicator. It never invents metrics: fields Telegram does not
expose stay zero and the assessment says "недостаточно данных" instead of
guessing.

The one strong signal available without a user session is the **participant bot
share**: audience scans record ``is_bot`` per member, so for a scanned source we
can report what share of the sample is bots. That is a real observation, not an
estimate of the whole channel.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import utcnow
from backend.app.db.models.audience import AudienceUser, SourceUserLink
from backend.app.db.models.donor import QUALITY_TITLES, DonorMetrics
from backend.app.db.repositories.audience import AudienceSourceRepository
from backend.app.db.repositories.donors import DonorRepository
from backend.app.services.donor_heuristics import DonorInput, assess_donor
from backend.app.services.events_service import EventsService

MODULE = "donors"


class DonorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sources = AudienceSourceRepository(session)
        self.repo = DonorRepository(session)
        self.events = EventsService(session)

    async def list_metrics(self) -> list[DonorMetrics]:
        return await self.repo.list_all()

    async def analyze(self, source_id: str) -> DonorMetrics:
        source = await self.sources.get(source_id)
        if source is None:
            raise ValueError("Источник не найден.")
        members = await self._count_members(source_id)
        bots = await self._count_bots(source_id)

        subscribers = int(source.reported_total or source.discovered_count or 0)
        completeness = str(source.completeness)
        data = DonorInput(
            subscribers=subscribers,
            posts_count=0,
            avg_views=0.0,
            participant_data=members > 0,
            sample_size=members,
            sample_bots=bots,
            completeness=completeness,
        )
        assessment = assess_donor(data)

        row = await self.repo.upsert(source_id)
        row.channel_id = source.channel_id
        row.title = source.title or source.username or source.reference
        row.subscribers = subscribers
        row.bot_probability = assessment.bot_probability
        row.confidence = assessment.confidence
        row.participant_data = assessment.participant_data
        row.bot_share_estimate = assessment.bot_share_estimate
        row.quality = assessment.quality
        row.quality_score = assessment.quality_score
        import json

        row.signals = json.dumps(assessment.signals, ensure_ascii=False)
        row.explanations = json.dumps(assessment.explanations, ensure_ascii=False)
        row.summary = assessment.summary
        row.source_completeness = completeness
        row.last_analyzed = utcnow()
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Источник проанализирован: {row.title}.",
            explanation=assessment.summary,
            operation="analyze",
            status="ok",
        )
        await self.session.commit()
        return row

    async def analyze_all(self) -> list[DonorMetrics]:
        results: list[DonorMetrics] = []
        sources, _ = await self.sources.list(limit=500)
        for source in sources:
            results.append(await self.analyze(source.id))
        return results

    # --- helpers -------------------------------------------------------------
    async def _count_members(self, source_id: str) -> int:
        stmt = select(func.count()).select_from(SourceUserLink).where(
            SourceUserLink.source_id == source_id
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def _count_bots(self, source_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(SourceUserLink)
            .join(AudienceUser, AudienceUser.id == SourceUserLink.user_id)
            .where(SourceUserLink.source_id == source_id, AudienceUser.is_bot.is_(True))
        )
        return int((await self.session.execute(stmt)).scalar_one())


def metrics_to_dict(row: DonorMetrics) -> dict[str, object]:
    """Serialise donor metrics for the API (no PII, no secrets)."""
    import json

    def _load(raw: str) -> list[str]:
        try:
            value = json.loads(raw or "[]")
        except (ValueError, TypeError):
            return []
        return [str(v) for v in value] if isinstance(value, list) else []

    return {
        "id": row.id,
        "source_id": row.source_id,
        "channel_id": row.channel_id,
        "title": row.title,
        "subscribers": row.subscribers,
        "quality": row.quality,
        "quality_title": QUALITY_TITLES.get(row.quality, row.quality),
        "quality_score": row.quality_score,
        "bot_probability": row.bot_probability,
        "confidence": row.confidence,
        "participant_data": row.participant_data,
        "bot_share_estimate": row.bot_share_estimate,
        "signals": _load(row.signals),
        "explanations": _load(row.explanations),
        "summary": row.summary,
        "source_completeness": row.source_completeness,
        "last_analyzed": (
            row.last_analyzed.isoformat() if row.last_analyzed else None
        ),
    }


__all__ = ["DonorService", "metrics_to_dict"]
