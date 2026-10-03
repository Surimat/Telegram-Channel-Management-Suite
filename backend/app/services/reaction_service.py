"""Reaction Service (PHASE 3).

Coordinates the Reaction Manager vertical slice:

* Profiles: CRUD over :class:`ReactionProfile` (UI-editable).
* Rules: CRUD over :class:`ReactionRule` + seed defaults.
* Posts: ingest a post → classify (Rules Engine) → plan → enqueue jobs.
* Execution: run a reaction job through the Telegram provider abstraction.
* Simulation: build a plan **without** touching Telegram.

Telegram access goes exclusively through :class:`TelegramBotProvider` (D-001);
this module never imports aiogram. Reaction jobs are durable: each planned job is
persisted and an underlying ``job_queue`` row drives execution, so unfinished
work is recovered after a restart (D-008).
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.types import (
    MODE_AUTO,
    SOURCE_AI,
    SOURCE_FALLBACK,
    SOURCE_MANUAL,
    SOURCE_RULES,
    ClassificationResult,
    Classifier,
)
from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret
from backend.app.db.base import utcnow
from backend.app.db.models.ai import AiRecord
from backend.app.db.models.bot import Bot, BotHealth, BotKind
from backend.app.db.models.post import Post, PostStatus
from backend.app.db.models.reaction import (
    DelayPresetDB,
    ReactionJob,
    ReactionJobStatus,
    ReactionProfile,
    ReactionRule,
)
from backend.app.db.repositories.ai import AiRepository
from backend.app.db.repositories.bots import BotRepository
from backend.app.db.repositories.posts import PostRepository
from backend.app.db.repositories.reactions import (
    ReactionJobRepository,
    ReactionProfileRepository,
    ReactionRuleRepository,
)
from backend.app.providers.base import TelegramBotProvider
from backend.app.providers.errors import FloodWaitError, TelegramProviderError
from backend.app.providers.registry import build_bot_provider
from backend.app.rules.defaults import default_rule_specs
from backend.app.rules.delays import DelayPreset
from backend.app.rules.engine import (
    CATEGORY_TITLES,
    Category,
    RuleMatch,
    RulesEngine,
    RuleSpec,
)
from backend.app.services.events_service import EventsService
from backend.app.services.queue_service import QueueService
from backend.app.services.reaction_planner import PlanParams, ReactionPlanner

ProviderFactory = Callable[..., TelegramBotProvider]

#: Queue job kind handled by the scheduler for reactions.
REACTION_JOB_KIND = "reaction.job"


class ReactionServiceError(Exception):
    """A reaction operation failed; carries a friendly message and a hint."""

    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class SimulationStep:
    bot_id: str
    bot_username: str
    emoji: str
    delay_seconds: float
    scheduled_at: datetime
    status: str


@dataclass(slots=True)
class SimulationResult:
    text: str
    category: str
    category_title: str
    confidence: float
    source: str
    tone: str
    mode: str
    ai_attempted: bool
    ai_used: bool
    fallback_used: bool
    ai_error: str
    allowed_reactions: list[str]
    preferred_reactions: list[str]
    forbidden_reactions: list[str]
    profile_id: str
    profile_name: str
    total_bots: int
    participating: int
    skipped: int
    steps: list[SimulationStep]


def _loads(raw: str, default: object) -> object:
    try:
        value = json.loads(raw) if raw else default
        return value if value is not None else default
    except json.JSONDecodeError:
        return default


DEFAULT_PROFILE_NAME = "Профиль по умолчанию"
DEFAULT_PROFILE_EMOJI = ["❤️", "👍", "🔥", "🙏", "😍"]


class ReactionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        provider_factory: ProviderFactory = build_bot_provider,
        rng: random.Random | None = None,
        classifier: Classifier | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.bots = BotRepository(session)
        self.posts = PostRepository(session)
        self.profiles = ReactionProfileRepository(session)
        self.rules = ReactionRuleRepository(session)
        self.jobs = ReactionJobRepository(session)
        self.events = EventsService(session)
        self.queue = QueueService(session)
        self.ai_repo = AiRepository(session)
        self.planner = ReactionPlanner()
        self._provider_factory = provider_factory
        # Injectable RNG keeps simulation/tests deterministic (D-021).
        self._rng = rng
        # PHASE 7: optional injected classifier (rules + AI router). When omitted,
        # the service builds a rules-only classifier lazily from DB rules.
        self._classifier = classifier

    def _rng_for(self, seed: int | None) -> random.Random:
        if seed is not None:
            return random.Random(seed)
        return self._rng or random.Random()

    # ======================================================================
    # Rules
    # ======================================================================
    async def ensure_default_rules(self) -> int:
        """Seed the editable rule set once. Returns how many were created."""
        existing = await self.rules.count()
        if existing:
            return 0
        for spec in default_rule_specs():
            await self.rules.add(self._rule_from_spec(spec))
        await self.session.commit()
        return len(default_rule_specs())

    @staticmethod
    def _rule_from_spec(spec: RuleSpec) -> ReactionRule:
        return ReactionRule(
            name=spec.name,
            category=str(spec.category),
            enabled=spec.enabled,
            priority=spec.priority,
            manual_override=spec.manual_override,
            language=spec.language,
            keywords=json.dumps(spec.keywords, ensure_ascii=False),
            phrases=json.dumps(spec.phrases, ensure_ascii=False),
            regexes=json.dumps(spec.regexes, ensure_ascii=False),
            exclusions=json.dumps(spec.exclusions, ensure_ascii=False),
            allowed_reactions=json.dumps(spec.allowed_reactions, ensure_ascii=False),
            preferred_reactions=json.dumps(spec.preferred_reactions, ensure_ascii=False),
            forbidden_reactions=json.dumps(spec.forbidden_reactions, ensure_ascii=False),
            min_confidence=spec.min_confidence,
        )

    @staticmethod
    def _spec_from_rule(rule: ReactionRule) -> RuleSpec:
        return RuleSpec(
            id=rule.id,
            name=rule.name,
            category=Category(rule.category),
            keywords=list(_loads(rule.keywords, [])),  # type: ignore[arg-type]
            phrases=list(_loads(rule.phrases, [])),  # type: ignore[arg-type]
            regexes=list(_loads(rule.regexes, [])),  # type: ignore[arg-type]
            exclusions=list(_loads(rule.exclusions, [])),  # type: ignore[arg-type]
            priority=rule.priority,
            enabled=rule.enabled,
            allowed_reactions=list(_loads(rule.allowed_reactions, [])),  # type: ignore[arg-type]
            preferred_reactions=list(_loads(rule.preferred_reactions, [])),  # type: ignore[arg-type]
            forbidden_reactions=list(_loads(rule.forbidden_reactions, [])),  # type: ignore[arg-type]
            min_confidence=rule.min_confidence,
            manual_override=rule.manual_override,
            language=rule.language,
        )

    async def list_rules(self) -> list[ReactionRule]:
        return await self.rules.list()

    async def get_rule(self, rule_id: str) -> ReactionRule | None:
        return await self.rules.get(rule_id)

    async def save_rule(self, rule_id: str | None, **fields: object) -> ReactionRule:
        if rule_id:
            rule = await self.rules.get(rule_id)
            if rule is None:
                raise ReactionServiceError("Правило не найдено.", status_code=404)
        else:
            rule = ReactionRule(category=str(fields.get("category", Category.NEUTRAL)))
            self.session.add(rule)
        for key in (
            "name",
            "category",
            "enabled",
            "priority",
            "manual_override",
            "language",
            "min_confidence",
        ):
            if key in fields and fields[key] is not None:
                setattr(rule, key, fields[key])
        for key in (
            "keywords",
            "phrases",
            "regexes",
            "exclusions",
            "allowed_reactions",
            "preferred_reactions",
            "forbidden_reactions",
        ):
            if key in fields and fields[key] is not None:
                setattr(rule, key, json.dumps(list(fields[key]), ensure_ascii=False))  # type: ignore[arg-type]
        await self.session.flush()
        await self.session.commit()
        return rule

    async def delete_rule(self, rule_id: str) -> None:
        rule = await self.rules.get(rule_id)
        if rule is None:
            raise ReactionServiceError("Правило не найдено.", status_code=404)
        await self.rules.delete(rule)
        await self.session.commit()

    # ======================================================================
    # Profiles
    # ======================================================================
    async def list_profiles(self) -> list[ReactionProfile]:
        return await self.profiles.list()

    async def get_profile(self, profile_id: str) -> ReactionProfile | None:
        return await self.profiles.get(profile_id)

    async def get_active_profile(self) -> ReactionProfile | None:
        return await self.profiles.get_active()

    async def resolve_profile(self, profile_id: str | None = None) -> ReactionProfile:
        """Pick the profile for preview/simulation, being forgiving.

        Order: explicit id → active profile → default profile (even if disabled)
        → any profile → create the default. Disabled profiles are still usable
        for a preview because a preview does not contact Telegram.
        """
        if profile_id:
            profile = await self.profiles.get(profile_id)
            if profile is not None:
                return profile
        profile = await self.get_active_profile()
        if profile is None:
            profile = await self.profiles.get_default()
        if profile is None:
            profiles = await self.profiles.list()
            profile = profiles[0] if profiles else None
        if profile is None:
            profile = await self.ensure_default_profile()
        return profile

    async def save_profile(self, profile_id: str | None, **fields: object) -> ReactionProfile:
        if profile_id:
            profile = await self.profiles.get(profile_id)
            if profile is None:
                raise ReactionServiceError("Профиль не найден.", status_code=404)
        else:
            profile = ReactionProfile(name=str(fields.get("name", "Новый профиль")))
            self.session.add(profile)
        if fields.get("name"):
            profile.name = str(fields["name"])
        if "description" in fields and fields["description"] is not None:
            profile.description = str(fields["description"])
        for key in ("enabled", "is_default", "max_bots_per_post"):
            if key in fields and fields[key] is not None:
                setattr(profile, key, fields[key])
        for key in ("participation_probability", "skip_probability", "delay_min", "delay_max"):
            if key in fields and fields[key] is not None:
                setattr(profile, key, float(fields[key]))  # type: ignore[arg-type]
        if fields.get("delay_preset"):
            profile.delay_preset = DelayPresetDB(str(fields["delay_preset"]))
        if "allowed_emoji" in fields and fields["allowed_emoji"] is not None:
            profile.allowed_emoji = json.dumps(list(fields["allowed_emoji"]), ensure_ascii=False)  # type: ignore[arg-type]
        if "emoji_weights" in fields and fields["emoji_weights"] is not None:
            profile.emoji_weights = json.dumps(dict(fields["emoji_weights"]), ensure_ascii=False)  # type: ignore[arg-type]

        # Column defaults are applied on flush; validate only once they exist.
        await self.session.flush()
        self._validate_profile(profile)

        if profile.is_default:
            await self.profiles.clear_defaults(except_id=profile.id)
        await self.session.flush()
        await self.session.commit()
        return profile

    @staticmethod
    def _validate_profile(profile: ReactionProfile) -> None:
        if not (0.0 <= profile.participation_probability <= 1.0):
            raise ReactionServiceError(
                "Вероятность участия бота должна быть от 0 до 100%.",
                how_to_fix="Укажите значение от 0 до 1 (например, 0.7 = 70%).",
            )
        if not (0.0 <= profile.skip_probability <= 1.0):
            raise ReactionServiceError(
                "Вероятность пропуска должна быть от 0 до 100%.",
                how_to_fix="Укажите значение от 0 до 1 (например, 0.1 = 10%).",
            )
        if profile.delay_max < profile.delay_min:
            raise ReactionServiceError(
                "Максимальная задержка меньше минимальной.",
                how_to_fix="Сделайте максимальную задержку не меньше минимальной.",
            )
        if profile.delay_min < 0:
            raise ReactionServiceError("Задержка не может быть отрицательной.")

    async def delete_profile(self, profile_id: str) -> None:
        profile = await self.profiles.get(profile_id)
        if profile is None:
            raise ReactionServiceError("Профиль не найден.", status_code=404)
        await self.profiles.delete(profile)
        await self.session.commit()

    async def set_reactions_enabled(self, enabled: bool) -> None:
        """Global switch: enable/disable the whole Reaction Manager."""
        profile = await self.get_active_profile()
        if profile is None:
            # If no profile exists yet, create the first default one.
            profile = await self.save_profile(
                None,
                name=DEFAULT_PROFILE_NAME,
                enabled=enabled,
                is_default=True,
                allowed_emoji=list(DEFAULT_PROFILE_EMOJI),
            )
        profile.enabled = enabled
        await self.session.flush()
        await self.session.commit()

    async def ensure_default_profile(self) -> ReactionProfile:
        """Guarantee a sensible default profile exists (best effort).

        Reactions stay disabled until the user explicitly enables them; this only
        makes the Profiles/Simulation screens usable on a fresh install.
        """
        profile = await self.get_active_profile()
        if profile is None:
            profile = await self.save_profile(
                None,
                name=DEFAULT_PROFILE_NAME,
                enabled=False,
                is_default=True,
                allowed_emoji=list(DEFAULT_PROFILE_EMOJI),
            )
        return profile

    async def reactions_enabled(self) -> bool:
        profile = await self.get_active_profile()
        return bool(profile and profile.enabled)

    # ======================================================================
    # Planning / simulation
    # ======================================================================
    @staticmethod
    def _plan_params(profile: ReactionProfile) -> PlanParams:
        return PlanParams(
            allowed_emoji=list(_loads(profile.allowed_emoji, [])),  # type: ignore[arg-type]
            emoji_weights=dict(_loads(profile.emoji_weights, {})),  # type: ignore[arg-type]
            participation_probability=profile.participation_probability,
            skip_probability=profile.skip_probability,
            delay_min=profile.delay_min,
            delay_max=profile.delay_max,
            delay_preset=DelayPreset(str(profile.delay_preset)),
            max_bots_per_post=profile.max_bots_per_post,
        )

    async def _rule_specs(self) -> list[RuleSpec]:
        rules = await self.rules.list(enabled=True)
        specs = [self._spec_from_rule(r) for r in rules]
        return specs or default_rule_specs()

    async def _get_classifier(self, mode: str) -> Classifier:
        """Return the classifier for ``mode`` (PHASE 7).

        An injected classifier (tests / pre-built router) always wins. Otherwise a
        router is built from the current DB rules plus the optional AI, honoring
        the requested mode.
        """
        if self._classifier is not None:
            return self._classifier
        from backend.app.ai.classifiers import RulesClassifier
        from backend.app.ai.router import RoutingClassifier
        from backend.app.services.ai_service import AiService

        specs = await self._rule_specs()
        rules_classifier = RulesClassifier(specs)
        ai = await AiService(self.session, settings=self.settings).classifier()
        return RoutingClassifier(
            rules=rules_classifier,
            ai=ai,
            rules_threshold=self.settings.ai_rules_threshold,
            ai_threshold=self.settings.ai_confidence_threshold,
            mode=mode,
        )

    async def _route(
        self, text: str, *, mode: str = MODE_AUTO
    ) -> tuple[ClassificationResult, object]:
        """Classify with rules-first routing; also return the routing outcome."""
        from backend.app.ai.router import RoutingClassifier
        from backend.app.ai.types import ClassificationContext

        engine = await self._get_classifier(mode)
        context = ClassificationContext(
            known_categories=tuple(c.value for c in Category),
        )
        if isinstance(engine, RoutingClassifier):
            outcome = engine.route(text, context)
            await self._record_classification(outcome)
            return outcome.result, outcome
        result = engine.classify(text, context)
        return result, None

    async def _record_classification(self, outcome: object) -> None:
        """Persist aggregate metrics + a recent record for one classification."""
        from backend.app.ai.router import RoutingOutcome

        if not isinstance(outcome, RoutingOutcome):
            return
        result = outcome.result
        is_ai = result.source == SOURCE_AI
        try:
            await self.ai_repo.bump(
                rules=1,
                ai=1 if is_ai else 0,
                fallback=1 if outcome.fallback_used and not is_ai else 0,
                manual=1 if result.source == SOURCE_MANUAL else 0,
                ai_error=1 if outcome.ai_error and not is_ai else 0,
                latency_ms=result.processing_time_ms,
            )
            if self.settings.ai_history_limit > 0:
                await self.ai_repo.add_record(
                    AiRecord(
                        source=result.source,
                        category=str(result.category),
                        tone=str(result.tone),
                        confidence=result.confidence,
                        model=result.model,
                        latency_ms=result.processing_time_ms,
                        mode=outcome.mode,
                        ok=not outcome.ai_error,
                        detail=outcome.ai_error[:200],
                    )
                )
                await self.ai_repo.trim_records(self.settings.ai_history_limit)
        except Exception:  # pragma: no cover - metrics must never break flow
            pass

    def _public_source(self, source: str) -> str:
        """Map internal source names to the public UI vocabulary."""
        if source in (SOURCE_RULES, SOURCE_MANUAL, SOURCE_AI, SOURCE_FALLBACK):
            return source
        if source == "default":
            return SOURCE_FALLBACK
        return SOURCE_RULES

    async def _policy_for_category(
        self, category: Category, specs: list[RuleSpec]
    ) -> tuple[list[str], list[str], list[str]]:
        """Reaction emoji policy for a category, from its rule or defaults.

        Emoji selection stays deterministic and rule-driven; AI never picks
        emoji (D-032).
        """
        from backend.app.rules.engine import DEFAULT_CATEGORY_REACTIONS

        candidate: RuleSpec | None = None
        for spec in specs:
            is_better = candidate is None or spec.priority > candidate.priority
            if spec.category == category and spec.enabled and is_better:
                candidate = spec
        if candidate is not None:
            allowed, preferred = RulesEngine._reaction_policy(candidate)
            return allowed, preferred, list(candidate.forbidden_reactions)
        default_allowed, default_preferred = DEFAULT_CATEGORY_REACTIONS[category]
        return list(default_allowed), list(default_preferred), []

    async def _result_to_match(
        self, result: ClassificationResult, outcome: object = None
    ) -> RuleMatch:
        """Adapt a classification result to the RuleMatch the planner consumes."""
        specs = await self._rule_specs()
        allowed, preferred, forbidden = await self._policy_for_category(
            result.category, specs
        )
        return RuleMatch(
            category=result.category,
            confidence=result.confidence,
            source=self._public_source(result.source),
            matched_terms=list(result.matched_terms),
            allowed_reactions=allowed,
            preferred_reactions=preferred,
            forbidden_reactions=forbidden,
        )

    async def active_bots(self) -> list[Bot]:
        bots, _ = await self.bots.list(enabled=True)
        # Any enabled bot with a token can react; exclude the manager bot which
        # is reserved for control, and bots without a usable token.
        usable_health = {BotHealth.OK, BotHealth.UNKNOWN}
        return [
            b
            for b in bots
            if b.kind != BotKind.MANAGER and b.has_token and b.health in usable_health
        ]

    async def simulate(
        self,
        *,
        text: str,
        profile_id: str | None = None,
        bot_count: int | None = None,
        seed: int | None = None,
        mode: str = MODE_AUTO,
    ) -> SimulationResult:
        """Build a plan for ``text`` without creating jobs or contacting Telegram.

        When no real bots exist, deterministic placeholder bots are used so the
        feature is always demonstrable in the UI. ``mode`` selects rules-only,
        AI-only or rules-first+AI classification (PHASE 7).
        """
        profile = await self.resolve_profile(profile_id)
        result, outcome = await self._route(text, mode=mode)
        match = await self._result_to_match(result, outcome)
        tone = str(getattr(result, "tone", "neutral"))
        ai_attempted = bool(getattr(outcome, "ai_attempted", False))
        ai_used = bool(getattr(outcome, "ai_used", False))
        fallback_used = bool(getattr(outcome, "fallback_used", False))
        ai_error = str(getattr(outcome, "ai_error", "") or "")

        bots = await self.active_bots()
        pairs = [(b.id, b.username or f"bot{b.telegram_id}") for b in bots]
        if not pairs:
            count = bot_count or 5
            pairs = [(f"demo-{i}", f"Bot {i:02d}") for i in range(1, count + 1)]

        base_time = utcnow()
        planned = self.planner.plan(
            post_id="simulation",
            bots=pairs,
            params=self._plan_params(profile),
            match=match,
            base_time=base_time,
            rng=self._rng_for(seed),
        )
        scheduled = [p for p in planned if p.status == "scheduled"]
        skipped = [p for p in planned if p.status == "skipped"]
        return SimulationResult(
            text=text,
            category=str(match.category),
            category_title=CATEGORY_TITLES.get(match.category, str(match.category)),
            confidence=match.confidence,
            source=match.source,
            tone=tone,
            mode=mode,
            ai_attempted=ai_attempted,
            ai_used=ai_used,
            fallback_used=fallback_used,
            ai_error=ai_error,
            allowed_reactions=match.allowed_reactions,
            preferred_reactions=match.preferred_reactions,
            forbidden_reactions=match.forbidden_reactions,
            profile_id=profile.id,
            profile_name=profile.name,
            total_bots=len(pairs),
            participating=len(scheduled),
            skipped=len(skipped),
            steps=[
                SimulationStep(
                    bot_id=p.bot_id,
                    bot_username=p.bot_username,
                    emoji=p.emoji,
                    delay_seconds=p.delay_seconds,
                    scheduled_at=p.scheduled_at,
                    status=p.status,
                )
                for p in planned
            ],
        )

    # ======================================================================
    # Post ingestion
    # ======================================================================
    async def ingest_post(
        self,
        *,
        text: str,
        telegram_message_id: int | None = None,
        channel_id: int | None = None,
        channel_username: str = "",
        posted_at: datetime | None = None,
        force_category: str | None = None,
        plan: bool = True,
        seed: int | None = None,
        mode: str = MODE_AUTO,
    ) -> Post:
        """Store a post, classify it and (optionally) enqueue reaction jobs."""
        result, outcome = await self._route(text, mode=mode)
        match = await self._result_to_match(result, outcome)
        if force_category:
            match = RuleMatch(
                category=Category(force_category),
                confidence=1.0,
                source=SOURCE_MANUAL,
                allowed_reactions=match.allowed_reactions,
                preferred_reactions=match.preferred_reactions,
                forbidden_reactions=match.forbidden_reactions,
            )
        post = Post(
            telegram_message_id=telegram_message_id,
            channel_id=channel_id,
            channel_username=channel_username,
            text=text,
            category=str(match.category),
            category_title=CATEGORY_TITLES.get(match.category, str(match.category)),
            classification_source=match.source,
            confidence=match.confidence,
            matched_terms=", ".join(match.matched_terms),
            status=PostStatus.CLASSIFIED,
            posted_at=posted_at,
        )
        await self.posts.add(post)
        await self.events.info(
            "reactions.reaction_service",
            f"Новый пост классифицирован как «{post.category_title}».",
            operation="ingest_post",
            status="ok",
        )
        if plan:
            try:
                await self.plan_post(post, seed=seed)
            except ReactionServiceError as exc:
                post.status = PostStatus.SKIPPED
                await self.events.warning(
                    "reactions.reaction_service",
                    "Реакции для поста не запланированы.",
                    explanation=exc.message,
                    how_to_fix=exc.how_to_fix,
                    operation="plan_post",
                    status="skipped",
                )
        await self.session.commit()
        return post

    async def plan_post(self, post: Post, *, seed: int | None = None) -> list[ReactionJob]:
        """Create durable reaction jobs for an already-stored post."""
        profile = await self.get_active_profile()
        if profile is None or not profile.enabled:
            raise ReactionServiceError(
                "Система реакций выключена.",
                how_to_fix="Включите реакции и создайте активный профиль в разделе «Реакции».",
                status_code=409,
            )
        bots = await self.active_bots()
        if not bots:
            raise ReactionServiceError(
                "Нет доступных ботов для реакций.",
                how_to_fix="Добавьте хотя бы одного обычного бота с действующим токеном.",
                status_code=409,
            )
        pairs = [(b.id, b.username or f"bot{b.telegram_id}") for b in bots]
        match = RuleMatch(
            category=Category(post.category) if post.category else Category.NEUTRAL,
            confidence=post.confidence,
            source=post.classification_source or "rules",
        )
        base_time = utcnow()
        planned = self.planner.plan(
            post_id=post.id,
            bots=pairs,
            params=self._plan_params(profile),
            match=match,
            base_time=base_time,
            rng=self._rng_for(seed),
        )

        created: list[ReactionJob] = []
        for step in planned:
            job = ReactionJob(
                post_id=post.id,
                bot_id=step.bot_id,
                profile_id=profile.id,
                reaction=step.emoji,
                status=(
                    ReactionJobStatus.SCHEDULED
                    if step.status == "scheduled"
                    else ReactionJobStatus.SKIPPED
                ),
                scheduled_at=step.scheduled_at,
            )
            await self.jobs.add(job)
            if step.status == "scheduled":
                queue_job = await self.queue.enqueue(
                    kind=REACTION_JOB_KIND,
                    payload={"reaction_job_id": job.id, "post_id": post.id, "bot_id": step.bot_id},
                    scheduled_at=step.scheduled_at,
                    group_key=post.id,
                    max_attempts=2,
                )
                job.queue_job_id = queue_job.id
                created.append(job)

        post.status = PostStatus.PLANNED
        await self.session.flush()
        await self.session.commit()
        await self.events.info(
            "reactions.reaction_service",
            f"Запланировано реакций: {len(created)}.",
            operation="plan_post",
            status="ok",
        )
        return created

    # ======================================================================
    # Execution (called by the durable scheduler)
    # ======================================================================
    async def execute_reaction_job(self, reaction_job_id: str) -> None:
        """Apply one reaction job via the provider. Raises on failure.

        FloodWait is *never* bypassed (D-006): the job is marked failed with a
        clear wait hint, and the error message surfaces in the UI.
        """
        job = await self.jobs.get(reaction_job_id)
        if job is None:
            raise ReactionServiceError("Задание реакции не найдено.", status_code=404)
        if job.status in {ReactionJobStatus.DONE, ReactionJobStatus.CANCELLED}:
            return
        if job.status == ReactionJobStatus.SKIPPED or not job.reaction:
            job.status = ReactionJobStatus.SKIPPED
            await self.session.flush()
            return

        post = await self.posts.get(job.post_id)
        bot = await self.bots.get(job.bot_id)
        if post is None or bot is None:
            raise ReactionServiceError("Пост или бот задания не найден.", status_code=404)
        if post.telegram_message_id is None or post.channel_id is None:
            raise ReactionServiceError(
                "У поста нет идентификатора сообщения в Telegram — реакция невозможна.",
                how_to_fix="Убедитесь, что пост получен из канала, а не создан вручную.",
            )

        job.status = ReactionJobStatus.RUNNING
        job.attempts += 1
        await self.session.flush()

        try:
            token = self._token_of(bot)
        except ReactionServiceError as exc:
            job.status = ReactionJobStatus.FAILED
            job.error = exc.message
            await self.session.flush()
            raise

        provider = self._provider_factory(
            token, provider_name=bot.provider_name, settings=self.settings
        )
        try:
            await provider.set_reaction(
                chat_id=post.channel_id,
                message_id=post.telegram_message_id,
                emoji=job.reaction,
            )
        except FloodWaitError as exc:
            job.status = ReactionJobStatus.FAILED
            job.error = f"FloodWait {exc.retry_after}s"
            await self.events.warning(
                "reactions.reaction_service",
                "Telegram попросил подождать перед реакцией.",
                explanation=exc.message,
                how_to_fix=exc.how_to_fix,
                actor=f"@{bot.username}" if bot.username else "",
                operation="set_reaction",
                status="flood_wait",
            )
            await self.session.flush()
            raise
        except TelegramProviderError as exc:
            job.status = ReactionJobStatus.FAILED
            job.error = exc.message
            await self.events.error(
                "reactions.reaction_service",
                "Не удалось поставить реакцию.",
                explanation=exc.message,
                how_to_fix=exc.how_to_fix,
                actor=f"@{bot.username}" if bot.username else "",
                operation="set_reaction",
                status="error",
            )
            await self.session.flush()
            raise
        else:
            job.status = ReactionJobStatus.DONE
            job.completed_at = utcnow()
            job.error = ""
            await self.session.flush()
        finally:
            await provider.close()

        await self._refresh_post_status(job.post_id)

    def _token_of(self, bot: Bot) -> str:
        if not bot.token_encrypted:
            raise ReactionServiceError(
                "У бота нет сохранённого токена.",
                how_to_fix="Проверьте бота в разделе «Боты».",
            )
        try:
            return open_secret(bot.token_encrypted, self.settings)
        except ValueError as exc:
            raise ReactionServiceError(
                "Не удалось прочитать токен бота.",
                how_to_fix="Проверьте, что APP_SECRET_KEY не менялся.",
            ) from exc

    async def _refresh_post_status(self, post_id: str) -> None:
        jobs = await self.jobs.for_post(post_id)
        if not jobs:
            return
        post = await self.posts.get(post_id)
        if post is None:
            return
        active = [
            j
            for j in jobs
            if j.status
            in {
                ReactionJobStatus.PLANNED,
                ReactionJobStatus.SCHEDULED,
                ReactionJobStatus.RUNNING,
            }
        ]
        if any(j.status == ReactionJobStatus.FAILED for j in jobs) and not active:
            post.status = PostStatus.FAILED
        elif not active:
            post.status = PostStatus.DONE
            post.processed_at = utcnow()
        await self.session.flush()

    # ======================================================================
    # Recovery (called at startup)
    # ======================================================================
    async def recover(self) -> int:
        """Reset reaction jobs left RUNNING after a crash back to scheduled."""
        return await self.jobs.recover_stuck_running()

    # ======================================================================
    # Stats / dashboard
    # ======================================================================
    async def stats(self) -> dict[str, object]:
        day_ago = utcnow() - timedelta(days=1)
        counts = await self.jobs.count_by_status()
        latest = await self.posts.latest()
        latest_count = len(await self.jobs.for_post(latest.id)) if latest else 0
        return {
            "enabled": await self.reactions_enabled(),
            "active_bots": len(await self.active_bots()),
            "queue_total": sum(
                counts.get(s, 0)
                for s in (
                    ReactionJobStatus.PLANNED,
                    ReactionJobStatus.SCHEDULED,
                    ReactionJobStatus.RUNNING,
                )
            ),
            "counts": counts,
            "planned_today": await self.jobs.count_created_since(day_ago),
            "done_today": await self.jobs.count_completed_since(day_ago),
            "failed_today": await self.jobs.count_failed_since(day_ago),
            "last_post": (
                {
                    "id": latest.id,
                    "category": latest.category,
                    "category_title": latest.category_title,
                    "created_at": latest.created_at,
                    "reactions": latest_count,
                }
                if latest
                else None
            ),
        }


__all__ = [
    "REACTION_JOB_KIND",
    "ReactionService",
    "ReactionServiceError",
    "SimulationResult",
    "SimulationStep",
]
