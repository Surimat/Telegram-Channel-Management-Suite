"""Application configuration.

Configuration comes from (in order of precedence):
1. Real environment variables / ``.env`` file.
2. Safe defaults defined here.

Secrets use :class:`pydantic.SecretStr` so they are never rendered by ``repr``
or accidental logging. The :func:`secret_values` helper exposes the raw secret
strings purely so the logging layer can register them for redaction — never use
it to print secrets.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.core import paths


class Settings(BaseSettings):
    """Strongly typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_debug: bool = False
    app_language: str = "ru"

    # --- Security ---
    app_secret_key: SecretStr = SecretStr("")
    app_cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    # --- Telegram manager bot ---
    manager_bot_token: SecretStr = SecretStr("")
    manager_bot_admin_ids: str = ""
    manager_bot_webhook_url: str = ""

    # --- Telegram user API ---
    telegram_api_id: str = ""
    telegram_api_hash: SecretStr = SecretStr("")

    # --- Sessions ---
    sessions_dir: str = "./sessions"

    # --- Scheduler ---
    scheduler_enabled: bool = True
    scheduler_timezone: str = "UTC"

    # --- Tiny AI ---
    ai_enabled: bool = False
    ai_model_path: str = ""
    ai_model_threads: int = 2

    # --- Logging ---
    log_level: str = "INFO"
    log_dir: str = "./logs"

    # --- Backup ---
    backup_dir: str = "./backups"

    @field_validator("app_port")
    @classmethod
    def _valid_port(cls, value: int) -> int:
        if not (1 <= value <= 65535):
            raise ValueError("app_port must be between 1 and 65535")
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return upper

    # --- Derived helpers ---
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.app_cors_origins.split(",") if o.strip()]

    @property
    def admin_ids(self) -> list[int]:
        result: list[int] = []
        for part in self.manager_bot_admin_ids.split(","):
            part = part.strip()
            if part.lstrip("-").isdigit():
                result.append(int(part))
        return result

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def resolve_sessions_dir(self) -> Path:
        p = Path(self.sessions_dir)
        return p if p.is_absolute() else (paths.project_root() / p).resolve()

    def resolve_log_dir(self) -> Path:
        p = Path(self.log_dir)
        return p if p.is_absolute() else (paths.project_root() / p).resolve()

    def resolve_backup_dir(self) -> Path:
        p = Path(self.backup_dir)
        return p if p.is_absolute() else (paths.project_root() / p).resolve()

    def resolve_database_url(self) -> str:
        """Resolve a relative SQLite path against the project root."""
        url = self.database_url
        prefix = "sqlite+aiosqlite:///"
        if url.startswith(prefix) and not url.startswith(prefix + "/"):
            rel = url[len(prefix) :]
            if not rel.startswith(":"):  # not :memory:
                abs_path = (paths.project_root() / rel).resolve()
                return prefix + str(abs_path)
        return url


def secret_values(settings: Settings) -> list[str]:
    """Return raw secret strings for the redaction registry.

    Callers must never log or return these values; they exist so the logging
    filter can mask them if they ever leak into a message.
    """
    candidates = [
        settings.app_secret_key,
        settings.manager_bot_token,
        settings.telegram_api_hash,
    ]
    values: list[str] = []
    for secret in candidates:
        raw = secret.get_secret_value() if isinstance(secret, SecretStr) else str(secret)
        if raw:
            values.append(raw)
    if settings.telegram_api_id:
        values.append(settings.telegram_api_id)
    return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache (used by tests)."""
    get_settings.cache_clear()
