"""Mini App API schemas (PHASE 9)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MiniAppConfig(BaseModel):
    enabled: bool = Field(description="Whether the Mini App feature is switched on.")
    available: bool = Field(description="Whether sign-in can actually succeed now.")
    bot_username: str = Field(default="", description="Manager bot username for the client.")
    public_url: str = Field(default="", description="Public HTTPS URL to register in BotFather.")
    reason: str = Field(default="", description="Plain-language explanation (RU).")
    how_to_fix: str = Field(default="", description="What the owner can do next.")


class MiniAppUserOut(BaseModel):
    id: int
    display_name: str
    username: str = ""
    language_code: str = ""
    photo_url: str = ""


class MiniAppAuthRequest(BaseModel):
    init_data: str = Field(
        default="",
        description="The raw Telegram WebApp initData string. Never logged.",
    )


class MiniAppAuthResponse(BaseModel):
    authenticated: bool = True
    is_admin: bool = False
    user: MiniAppUserOut
    expires_in: int = Field(description="Session lifetime in seconds.")


class MiniAppMeResponse(BaseModel):
    authenticated: bool
    is_admin: bool = False
    telegram_id: int | None = None
    expires_at: int | None = None


class MiniAppSetupRequest(BaseModel):
    public_url: str = Field(
        default="",
        description="Public HTTPS URL to register as the bot's Web App menu button.",
    )


class MiniAppSetupResponse(BaseModel):
    ok: bool = Field(description="Whether the Mini App was registered successfully.")
    message: str = Field(description="Plain-language result (RU).")
    how_to_fix: str = Field(default="", description="What the owner can do next.")
