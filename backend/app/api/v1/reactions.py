"""Reaction Manager router (PHASE 3).

Sections: profile CRUD, rule CRUD, post ingestion, simulation/preview, job
listing and statistics. Telegram execution is performed by the durable scheduler
through the provider abstraction — this router never calls Telegram directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_reaction_service
from backend.app.api.schemas.common import Page
from backend.app.api.schemas.reactions import (
    CategoryInfo,
    PostCreate,
    PostOut,
    ReactionJobOut,
    ReactionProfileIn,
    ReactionProfileOut,
    ReactionRuleIn,
    ReactionRuleOut,
    ReactionStats,
    SimulationIn,
    SimulationOut,
    SimulationStepOut,
)
from backend.app.core.logging import get_logger
from backend.app.db.models.reaction import ReactionJobStatus
from backend.app.db.session import get_session
from backend.app.rules.engine import CATEGORY_TITLES
from backend.app.services.reaction_service import ReactionService, ReactionServiceError

logger = get_logger(__name__)

router = APIRouter(prefix="/reactions", tags=["reactions"])


def _http(exc: ReactionServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _human_delay(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds} сек"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}:{sec:02d}"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{sec:02d}"


@router.get("/categories", response_model=list[CategoryInfo])
async def list_categories() -> list[CategoryInfo]:
    return [CategoryInfo(key=str(c), title=t) for c, t in CATEGORY_TITLES.items()]


# --------------------------------------------------------------------------
# Profiles
# --------------------------------------------------------------------------
@router.get("/profiles", response_model=list[ReactionProfileOut])
async def list_profiles(
    service: ReactionService = Depends(get_reaction_service),
) -> list[ReactionProfileOut]:
    profiles = await service.list_profiles()
    return [await _profile_out(service, p) for p in profiles]


@router.post("/profiles", response_model=ReactionProfileOut)
async def create_profile(
    payload: ReactionProfileIn,
    service: ReactionService = Depends(get_reaction_service),
) -> ReactionProfileOut:
    try:
        profile = await service.save_profile(None, **payload.model_dump(exclude_none=True))
    except ReactionServiceError as exc:
        raise _http(exc) from exc
    return await _profile_out(service, profile)


@router.patch("/profiles/{profile_id}", response_model=ReactionProfileOut)
async def update_profile(
    profile_id: str,
    payload: ReactionProfileIn,
    service: ReactionService = Depends(get_reaction_service),
) -> ReactionProfileOut:
    try:
        profile = await service.save_profile(profile_id, **payload.model_dump(exclude_none=True))
    except ReactionServiceError as exc:
        raise _http(exc) from exc
    return await _profile_out(service, profile)


@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: str,
    service: ReactionService = Depends(get_reaction_service),
) -> dict[str, str]:
    try:
        await service.delete_profile(profile_id)
    except ReactionServiceError as exc:
        raise _http(exc) from exc
    return {"status": "deleted"}


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------
@router.get("/rules", response_model=list[ReactionRuleOut])
async def list_rules(
    service: ReactionService = Depends(get_reaction_service),
) -> list[ReactionRuleOut]:
    rules = await service.list_rules()
    return [ReactionRuleOut.from_model(r) for r in rules]


@router.post("/rules", response_model=ReactionRuleOut)
async def create_rule(
    payload: ReactionRuleIn,
    service: ReactionService = Depends(get_reaction_service),
) -> ReactionRuleOut:
    try:
        rule = await service.save_rule(None, **payload.model_dump(exclude_none=True))
    except ReactionServiceError as exc:
        raise _http(exc) from exc
    return ReactionRuleOut.from_model(rule)


@router.patch("/rules/{rule_id}", response_model=ReactionRuleOut)
async def update_rule(
    rule_id: str,
    payload: ReactionRuleIn,
    service: ReactionService = Depends(get_reaction_service),
) -> ReactionRuleOut:
    try:
        rule = await service.save_rule(rule_id, **payload.model_dump(exclude_none=True))
    except ReactionServiceError as exc:
        raise _http(exc) from exc
    return ReactionRuleOut.from_model(rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    service: ReactionService = Depends(get_reaction_service),
) -> dict[str, str]:
    try:
        await service.delete_rule(rule_id)
    except ReactionServiceError as exc:
        raise _http(exc) from exc
    return {"status": "deleted"}


# --------------------------------------------------------------------------
# Simulation / preview
# --------------------------------------------------------------------------
@router.post("/simulate", response_model=SimulationOut)
async def simulate(
    payload: SimulationIn,
    service: ReactionService = Depends(get_reaction_service),
) -> SimulationOut:
    """Build a plan without contacting Telegram. The key UI feature."""
    try:
        result = await service.simulate(
            text=payload.text,
            profile_id=payload.profile_id,
            bot_count=payload.bot_count,
            seed=payload.seed,
            mode=payload.mode,
        )
    except ReactionServiceError as exc:
        raise _http(exc) from exc
    return SimulationOut(
        text=result.text,
        category=result.category,
        category_title=result.category_title,
        confidence=result.confidence,
        source=result.source,
        tone=result.tone,
        mode=result.mode,
        ai_attempted=result.ai_attempted,
        ai_used=result.ai_used,
        fallback_used=result.fallback_used,
        ai_error=result.ai_error,
        allowed_reactions=result.allowed_reactions,
        preferred_reactions=result.preferred_reactions,
        forbidden_reactions=result.forbidden_reactions,
        profile_id=result.profile_id,
        profile_name=result.profile_name,
        total_bots=result.total_bots,
        participating=result.participating,
        skipped=result.skipped,
        steps=[
            SimulationStepOut(
                bot_id=s.bot_id,
                bot_username=s.bot_username,
                emoji=s.emoji,
                delay_seconds=s.delay_seconds,
                scheduled_at=s.scheduled_at,
                status=s.status,
                delay_human=_human_delay(s.delay_seconds) if s.status == "scheduled" else "—",
            )
            for s in result.steps
        ],
    )


# --------------------------------------------------------------------------
# Posts
# --------------------------------------------------------------------------
@router.get("/posts", response_model=Page[PostOut])
async def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> Page[PostOut]:
    service = ReactionService(session)
    offset = (page - 1) * page_size
    rows, total = await service.posts.list(limit=page_size, offset=offset)
    return Page[PostOut](
        items=[PostOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/posts", response_model=PostOut)
async def create_post(
    payload: PostCreate,
    service: ReactionService = Depends(get_reaction_service),
) -> PostOut:
    """Ingest a post: classify it and (optionally) plan reactions."""
    try:
        post = await service.ingest_post(
            text=payload.text,
            telegram_message_id=payload.telegram_message_id,
            channel_id=payload.channel_id,
            channel_username=payload.channel_username,
            registry_channel_id=payload.registry_channel_id,
            force_category=payload.force_category,
            plan=payload.plan,
            mode=payload.mode,
        )
    except ReactionServiceError as exc:
        raise _http(exc) from exc
    return PostOut.model_validate(post)


@router.post("/posts/{post_id}/plan", response_model=list[ReactionJobOut])
async def plan_post(
    post_id: str,
    session: AsyncSession = Depends(get_session),
    service: ReactionService = Depends(get_reaction_service),
) -> list[ReactionJobOut]:
    post = await service.posts.get(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Пост не найден.")
    try:
        jobs = await service.plan_post(post)
    except ReactionServiceError as exc:
        raise _http(exc) from exc
    return [ReactionJobOut.model_validate(j) for j in jobs]


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------
@router.get("/jobs", response_model=Page[ReactionJobOut])
async def list_jobs(
    status: ReactionJobStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> Page[ReactionJobOut]:
    service = ReactionService(session)
    offset = (page - 1) * page_size
    rows, total = await service.jobs.list(status=status, limit=page_size, offset=offset)
    return Page[ReactionJobOut](
        items=[ReactionJobOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# --------------------------------------------------------------------------
# Settings switch + stats
# --------------------------------------------------------------------------
@router.get("/status", response_model=ReactionStats)
async def reaction_status(
    service: ReactionService = Depends(get_reaction_service),
) -> ReactionStats:
    stats = await service.stats()
    return ReactionStats.model_validate(stats)


@router.post("/enable", response_model=ReactionStats)
async def enable_reactions(
    service: ReactionService = Depends(get_reaction_service),
) -> ReactionStats:
    await service.set_reactions_enabled(True)
    return ReactionStats.model_validate(await service.stats())


@router.post("/disable", response_model=ReactionStats)
async def disable_reactions(
    service: ReactionService = Depends(get_reaction_service),
) -> ReactionStats:
    await service.set_reactions_enabled(False)
    return ReactionStats.model_validate(await service.stats())


async def _profile_out(
    service: ReactionService, profile: object
) -> ReactionProfileOut:
    import json

    def _arr(raw: str) -> list[str]:
        try:
            return list(json.loads(raw or "[]"))
        except json.JSONDecodeError:
            return []

    def _obj(raw: str) -> dict[str, float]:
        try:
            data = json.loads(raw or "{}")
            return {k: float(v) for k, v in dict(data).items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    return ReactionProfileOut(
        id=profile.id,  # type: ignore[attr-defined]
        name=profile.name,  # type: ignore[attr-defined]
        description=profile.description,  # type: ignore[attr-defined]
        enabled=profile.enabled,  # type: ignore[attr-defined]
        is_default=profile.is_default,  # type: ignore[attr-defined]
        allowed_emoji=_arr(profile.allowed_emoji),  # type: ignore[attr-defined]
        emoji_weights=_obj(profile.emoji_weights),  # type: ignore[attr-defined]
        participation_probability=profile.participation_probability,  # type: ignore[attr-defined]
        skip_probability=profile.skip_probability,  # type: ignore[attr-defined]
        delay_min=profile.delay_min,  # type: ignore[attr-defined]
        delay_max=profile.delay_max,  # type: ignore[attr-defined]
        delay_preset=str(profile.delay_preset.value),  # type: ignore[attr-defined]
        max_bots_per_post=profile.max_bots_per_post,  # type: ignore[attr-defined]
        created_at=profile.created_at,  # type: ignore[attr-defined]
        updated_at=profile.updated_at,  # type: ignore[attr-defined]
    )
