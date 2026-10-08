"""Reusable AI profiles (Content Operations 2.0, requirement 12).

A profile is *data*, not logic: it names a set of system instructions, a
language, a tone, a max length, a provider policy and the pipeline actions to
apply. Business code asks a profile for its instructions instead of hardcoding a
prompt, so the owner can tune the pipeline without a code change.

Built-in profiles are seeded on demand (idempotently) so a fresh install has
useful starting points; they are marked ``builtin`` and can still be edited.
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.content_ops import AiProfile
from backend.app.db.repositories.content_ops import AiProfileRepository

MODULE = "content"

#: Provider policies mirror the AI Gateway routing strategies. ``auto`` lets the
#: router pick (local/free first), never a promise of a specific provider.
VALID_POLICIES = frozenset(
    {"auto", "free_first", "cheapest", "fastest", "best_quality", "manual"}
)

#: The fixed action vocabulary a profile may request (never arbitrary scripting).
ACTION_REWRITE = "rewrite"
ACTION_SUMMARIZE = "summarize"
ACTION_TRANSLATE = "translate"
ACTION_CLASSIFY = "classify"
ACTION_MODERATION = "moderation"
ACTION_TITLE = "title"
ACTION_DESCRIPTION = "description"
ACTION_FIRST_COMMENT = "first_comment"

VALID_ACTIONS = (
    ACTION_REWRITE,
    ACTION_SUMMARIZE,
    ACTION_TRANSLATE,
    ACTION_CLASSIFY,
    ACTION_MODERATION,
    ACTION_TITLE,
    ACTION_DESCRIPTION,
    ACTION_FIRST_COMMENT,
)


def _instructions(body: str) -> str:
    return (
        "Ты помощник редактора Telegram-канала. Отвечай по-русски, кратко и по делу. "
        "Не выдумывай факты.\n" + body
    )


#: Built-in profiles (requirement 12: News, Neutral, Cynical, Informative,
#: Short, Long, Telegram style). Never secret; prompts are plain data.
BUILTIN_PROFILES: tuple[dict[str, object], ...] = (
    {
        "key": "news",
        "title": "Новости",
        "tone": "neutral",
        "max_length": 900,
        "description": "Сухой новостной тон, факты без лишних эмоций.",
        "actions": [ACTION_REWRITE, ACTION_TITLE],
        "system_instructions": _instructions(
            "Стиль: новостной. Начни с сути, укажи факты, избегай оценок."
        ),
    },
    {
        "key": "neutral",
        "title": "Нейтральный",
        "tone": "neutral",
        "max_length": 700,
        "description": "Ровный нейтральный тон без окраски.",
        "actions": [ACTION_REWRITE],
        "system_instructions": _instructions("Стиль: нейтральный. Без эмоций и оценок."),
    },
    {
        "key": "cynical",
        "title": "Циничный",
        "tone": "cynical",
        "max_length": 700,
        "description": "Ироничный, сдержанно-циничный тон.",
        "actions": [ACTION_REWRITE],
        "system_instructions": _instructions(
            "Стиль: лёгкий цинизм и ирония, но без оскорблений."
        ),
    },
    {
        "key": "informative",
        "title": "Информативный",
        "tone": "neutral",
        "max_length": 1100,
        "description": "Подробно и по делу, с пояснениями.",
        "actions": [ACTION_REWRITE, ACTION_SUMMARIZE],
        "system_instructions": _instructions(
            "Стиль: информативный. Поясняй контекст, добавляй полезные детали."
        ),
    },
    {
        "key": "short",
        "title": "Короткий",
        "tone": "neutral",
        "max_length": 280,
        "description": "Максимально кратко, одно-два предложения.",
        "actions": [ACTION_SUMMARIZE],
        "system_instructions": _instructions("Стиль: очень кратко. Только суть."),
    },
    {
        "key": "long",
        "title": "Длинный",
        "tone": "neutral",
        "max_length": 1800,
        "description": "Развёрнутый материал с деталями.",
        "actions": [ACTION_REWRITE, ACTION_DESCRIPTION],
        "system_instructions": _instructions("Стиль: развёрнутый. Раскрой тему подробно."),
    },
    {
        "key": "telegram",
        "title": "Telegram-стиль",
        "tone": "warm",
        "max_length": 700,
        "description": "Живой разговорный стиль Telegram.",
        "actions": [ACTION_REWRITE, ACTION_FIRST_COMMENT],
        "system_instructions": _instructions(
            "Стиль: живой, разговорный, как в Telegram. Короткие абзацы, эмодзи уместны."
        ),
    },
)


class ProfileError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


def _parse_actions(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(a) for a in value if str(a) in VALID_ACTIONS]


class AiProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.profiles = AiProfileRepository(session)

    async def ensure_builtin(self) -> None:
        """Seed the built-in profiles once (idempotent)."""
        existing = {p.key for p in await self.profiles.list_all()}
        created = False
        for spec in BUILTIN_PROFILES:
            if spec["key"] in existing:
                continue
            self.session.add(
                AiProfile(
                    key=str(spec["key"]),
                    title=str(spec["title"]),
                    language="ru",
                    tone=str(spec["tone"]),
                    max_length=int(spec["max_length"]),  # type: ignore[arg-type]
                    system_instructions=str(spec["system_instructions"]),
                    provider_policy="auto",
                    actions=json.dumps(spec["actions"], ensure_ascii=False),
                    builtin=True,
                    description=str(spec["description"]),
                )
            )
            created = True
        if created:
            await self.session.flush()
            await self.session.commit()

    async def list_profiles(self) -> list[AiProfile]:
        await self.ensure_builtin()
        return await self.profiles.list_all()

    async def get_by_key(self, key: str) -> AiProfile | None:
        await self.ensure_builtin()
        return await self.profiles.get_by_key(key)

    async def create(
        self,
        *,
        key: str,
        title: str,
        language: str = "ru",
        tone: str = "neutral",
        max_length: int = 0,
        system_instructions: str = "",
        provider_policy: str = "auto",
        actions: list[str] | None = None,
        description: str = "",
    ) -> AiProfile:
        key = (key or "").strip()
        if not key:
            raise ProfileError("Укажите ключ профиля.", how_to_fix="Например: my_news.")
        if await self.profiles.get_by_key(key) is not None:
            raise ProfileError("Профиль с таким ключом уже существует.")
        if provider_policy not in VALID_POLICIES:
            raise ProfileError(
                "Неизвестная политика провайдера.",
                how_to_fix="Допустимо: " + ", ".join(sorted(VALID_POLICIES)) + ".",
            )
        chosen = [a for a in (actions or []) if a in VALID_ACTIONS]
        profile = AiProfile(
            key=key,
            title=(title or "").strip() or key,
            language=language or "ru",
            tone=tone or "neutral",
            max_length=max(0, int(max_length or 0)),
            system_instructions=system_instructions or "",
            provider_policy=provider_policy,
            actions=json.dumps(chosen, ensure_ascii=False),
            description=description or "",
        )
        await self.profiles.add(profile)
        await self.session.commit()
        return profile

    async def update(self, profile_id: str, **fields: object) -> AiProfile:
        profile = await self.profiles.get(profile_id)
        if profile is None:
            raise ProfileError("Профиль не найден.", status_code=404)
        if fields.get("title") is not None:
            profile.title = str(fields["title"])
        if fields.get("language") is not None:
            profile.language = str(fields["language"])
        if fields.get("tone") is not None:
            profile.tone = str(fields["tone"])
        if fields.get("max_length") is not None:
            profile.max_length = max(0, int(fields["max_length"]))  # type: ignore[arg-type]
        if fields.get("system_instructions") is not None:
            profile.system_instructions = str(fields["system_instructions"])
        if fields.get("provider_policy") is not None:
            policy = str(fields["provider_policy"])
            if policy not in VALID_POLICIES:
                raise ProfileError("Неизвестная политика провайдера.")
            profile.provider_policy = policy
        if fields.get("actions") is not None:
            raw = fields["actions"]
            actions = [str(a) for a in raw] if isinstance(raw, list) else []  # type: ignore[union-attr]
            profile.actions = json.dumps(
                [a for a in actions if a in VALID_ACTIONS], ensure_ascii=False
            )
        if fields.get("enabled") is not None:
            profile.enabled = bool(fields["enabled"])
        if fields.get("description") is not None:
            profile.description = str(fields["description"])
        await self.session.flush()
        await self.session.commit()
        return profile

    async def delete(self, profile_id: str) -> None:
        profile = await self.profiles.get(profile_id)
        if profile is None:
            raise ProfileError("Профиль не найден.", status_code=404)
        if profile.builtin:
            raise ProfileError(
                "Встроенный профиль нельзя удалить.",
                how_to_fix="Отключите его или создайте собственный.",
            )
        await self.profiles.delete(profile)
        await self.session.commit()

    def actions_of(self, profile: AiProfile | None) -> list[str]:
        return _parse_actions(profile.actions) if profile else []


__all__ = [
    "ACTION_CLASSIFY",
    "ACTION_DESCRIPTION",
    "ACTION_FIRST_COMMENT",
    "ACTION_MODERATION",
    "ACTION_REWRITE",
    "ACTION_SUMMARIZE",
    "ACTION_TITLE",
    "ACTION_TRANSLATE",
    "BUILTIN_PROFILES",
    "VALID_ACTIONS",
    "VALID_POLICIES",
    "AiProfileService",
    "ProfileError",
]
