"""Reaction Manager API schemas (RU-first).

These are the public shapes for profiles, rules, posts, jobs, statistics and
simulation. Help text for complex settings is carried in ``*_help`` fields so the
UI can show "what it does / what it affects / safe default" without hardcoding.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReactionProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str = ""
    enabled: bool
    is_default: bool
    allowed_emoji: list[str] = Field(default_factory=list)
    emoji_weights: dict[str, float] = Field(default_factory=dict)
    participation_probability: float
    skip_probability: float
    delay_min: float
    delay_max: float
    delay_preset: str
    max_bots_per_post: int
    created_at: datetime
    updated_at: datetime


class ReactionProfileIn(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    allowed_emoji: list[str] | None = None
    emoji_weights: dict[str, float] | None = None
    participation_probability: float | None = Field(default=None, ge=0, le=1)
    skip_probability: float | None = Field(default=None, ge=0, le=1)
    delay_min: float | None = Field(default=None, ge=0)
    delay_max: float | None = Field(default=None, ge=0)
    delay_preset: str | None = None
    max_bots_per_post: int | None = Field(default=None, ge=0)


class ReactionSettingHelp(BaseModel):
    key: str
    title: str
    what_it_does: str
    what_it_affects: str
    safe_default: str


class ReactionRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    enabled: bool
    priority: int
    manual_override: bool
    language: str
    keywords: list[str] = Field(default_factory=list)
    phrases: list[str] = Field(default_factory=list)
    regexes: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    allowed_reactions: list[str] = Field(default_factory=list)
    preferred_reactions: list[str] = Field(default_factory=list)
    forbidden_reactions: list[str] = Field(default_factory=list)
    min_confidence: float
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, rule: object) -> ReactionRuleOut:
        import json

        def _arr(raw: str) -> list[str]:
            try:
                return list(json.loads(raw or "[]"))
            except json.JSONDecodeError:
                return []

        return cls(
            id=rule.id,  # type: ignore[attr-defined]
            name=rule.name,  # type: ignore[attr-defined]
            category=rule.category,  # type: ignore[attr-defined]
            enabled=rule.enabled,  # type: ignore[attr-defined]
            priority=rule.priority,  # type: ignore[attr-defined]
            manual_override=rule.manual_override,  # type: ignore[attr-defined]
            language=rule.language,  # type: ignore[attr-defined]
            keywords=_arr(rule.keywords),  # type: ignore[attr-defined]
            phrases=_arr(rule.phrases),  # type: ignore[attr-defined]
            regexes=_arr(rule.regexes),  # type: ignore[attr-defined]
            exclusions=_arr(rule.exclusions),  # type: ignore[attr-defined]
            allowed_reactions=_arr(rule.allowed_reactions),  # type: ignore[attr-defined]
            preferred_reactions=_arr(rule.preferred_reactions),  # type: ignore[attr-defined]
            forbidden_reactions=_arr(rule.forbidden_reactions),  # type: ignore[attr-defined]
            min_confidence=rule.min_confidence,  # type: ignore[attr-defined]
            created_at=rule.created_at,  # type: ignore[attr-defined]
            updated_at=rule.updated_at,  # type: ignore[attr-defined]
        )


class ReactionRuleIn(BaseModel):
    name: str | None = None
    category: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    manual_override: bool | None = None
    language: str | None = None
    keywords: list[str] | None = None
    phrases: list[str] | None = None
    regexes: list[str] | None = None
    exclusions: list[str] | None = None
    allowed_reactions: list[str] | None = None
    preferred_reactions: list[str] | None = None
    forbidden_reactions: list[str] | None = None
    min_confidence: float | None = Field(default=None, ge=0, le=1)


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    telegram_message_id: int | None = None
    channel_id: int | None = None
    channel_username: str = ""
    text: str = ""
    category: str = ""
    category_title: str = ""
    classification_source: str = ""
    confidence: float = 0.0
    matched_terms: str = ""
    status: str
    posted_at: datetime | None = None
    processed_at: datetime | None = None
    created_at: datetime


class PostCreate(BaseModel):
    text: str = Field(description="Текст поста для классификации и планирования.")
    telegram_message_id: int | None = None
    channel_id: int | None = None
    channel_username: str = ""
    force_category: str | None = Field(
        default=None, description="Ручное указание категории (переопределяет правила)."
    )
    plan: bool = Field(default=True, description="Сразу запланировать реакции.")
    mode: str = Field(
        default="auto",
        description="Способ: auto (правила+ИИ), rules (только правила), ai (только ИИ).",
    )


class ReactionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    post_id: str
    bot_id: str
    profile_id: str = ""
    reaction: str = ""
    status: str
    scheduled_at: datetime | None = None
    completed_at: datetime | None = None
    attempts: int
    error: str = ""
    created_at: datetime


class SimulationStepOut(BaseModel):
    bot_id: str
    bot_username: str
    emoji: str
    delay_seconds: float
    scheduled_at: datetime
    status: str
    delay_human: str = ""


class SimulationOut(BaseModel):
    text: str
    category: str
    category_title: str
    confidence: float
    source: str
    tone: str = "neutral"
    mode: str = "auto"
    ai_attempted: bool = False
    ai_used: bool = False
    fallback_used: bool = False
    ai_error: str = ""
    allowed_reactions: list[str]
    preferred_reactions: list[str]
    forbidden_reactions: list[str]
    profile_id: str
    profile_name: str
    total_bots: int
    participating: int
    skipped: int
    steps: list[SimulationStepOut]


class SimulationIn(BaseModel):
    text: str = Field(description="Текст поста для симуляции.")
    profile_id: str | None = None
    bot_count: int | None = Field(
        default=None, ge=1, le=50, description="Сколько ботов использовать, если реальных нет."
    )
    seed: int | None = Field(default=None, description="Зерно для воспроизводимости.")
    mode: str = Field(
        default="auto",
        description="Способ: auto (правила+ИИ), rules (только правила), ai (только ИИ).",
    )


class ReactionLastPost(BaseModel):
    id: str
    category: str
    category_title: str
    created_at: datetime
    reactions: int


class ReactionStats(BaseModel):
    enabled: bool
    active_bots: int
    queue_total: int
    planned_today: int
    done_today: int
    failed_today: int
    counts: dict[str, int] = Field(default_factory=dict)
    last_post: ReactionLastPost | None = None


class CategoryInfo(BaseModel):
    key: str
    title: str
