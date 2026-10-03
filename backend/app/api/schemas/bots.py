"""Bot API schemas.

Responses NEVER include the bot token or its sealed form (decision D-010);
``has_token`` indicates whether a credential is stored.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    enabled: bool
    telegram_id: int | None = None
    username: str = ""
    title: str = ""
    has_token: bool = False
    owner_id: int | None = None
    owner_username: str = ""
    can_manage_bots: bool | None = None
    health: str
    health_message: str = ""
    health_hint: str = ""
    last_error: str = ""
    last_health_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, bot: object) -> BotOut:
        return cls(
            id=bot.id,  # type: ignore[attr-defined]
            kind=bot.kind.value,  # type: ignore[attr-defined]
            enabled=bot.enabled,  # type: ignore[attr-defined]
            telegram_id=bot.telegram_id,  # type: ignore[attr-defined]
            username=bot.username,  # type: ignore[attr-defined]
            title=bot.title,  # type: ignore[attr-defined]
            has_token=bot.has_token,  # type: ignore[attr-defined]
            owner_id=bot.owner_id,  # type: ignore[attr-defined]
            owner_username=bot.owner_username,  # type: ignore[attr-defined]
            can_manage_bots=bot.can_manage_bots,  # type: ignore[attr-defined]
            health=bot.health.value,  # type: ignore[attr-defined]
            health_message=bot.health_message,  # type: ignore[attr-defined]
            health_hint=bot.health_hint,  # type: ignore[attr-defined]
            last_error=bot.last_error,  # type: ignore[attr-defined]
            last_health_at=bot.last_health_at,  # type: ignore[attr-defined]
            created_at=bot.created_at,  # type: ignore[attr-defined]
            updated_at=bot.updated_at,  # type: ignore[attr-defined]
        )


class BotCreate(BaseModel):
    token: str = Field(description="Токен бота из @BotFather.")
    kind: str = Field(default="ordinary", description="manager | managed | ordinary")
    title: str = ""
    provider_name: str | None = None


class BotHealthOut(BaseModel):
    bot_id: str
    ok: bool
    status: str
    message: str
    how_to_fix: str = ""
    username: str = ""
    telegram_id: int | None = None


class ManagedBotRegister(BaseModel):
    """Record a managed bot creation (from a Telegram ``managed_bot`` update)."""

    user_id: int
    username: str = ""
    title: str = ""
    owner_id: int | None = None
    owner_username: str = ""


class ManagedBotPreview(BaseModel):
    """A locally known managed bot plus the official user link to create one."""

    bot: BotOut | None = None
    create_link: str = ""
    instructions: str = ""


class BotSummary(BaseModel):
    total: int
    by_kind: dict[str, int]
    manager_connected: bool
    manager_username: str = ""
    manager_health: str = "unknown"
