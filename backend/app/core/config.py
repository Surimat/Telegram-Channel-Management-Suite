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
    # "auto" (real), "aiogram", or "fake". "auto" uses the fake provider when
    # offline_mode is enabled, so the app runs without any credentials.
    telegram_provider: str = "auto"
    offline_mode: bool = False

    # --- Telegram user API ---
    telegram_api_id: str = ""
    telegram_api_hash: SecretStr = SecretStr("")

    # --- Sessions ---
    sessions_dir: str = "./sessions"

    # --- Audience (PHASE 5) ---
    # Where generated exports are written (git-ignored, outside the DB).
    exports_dir: str = "./exports"
    # Delete export files older than this many days (0 disables cleanup).
    export_retention_days: int = 30
    # Store masked phone numbers for audience members when Telegram exposes them.
    # Off by default: collect only the personal data that is actually needed.
    audience_store_pii: bool = False
    # How many users to process per scheduler tick while scanning a source. Keeps
    # memory flat on weak machines and makes pause/cancel responsive.
    audience_scan_chunk_size: int = 500
    # Participants requested per Telegram page during a scan.
    audience_scan_batch_size: int = 100
    # Safety cap on users per scan (0 = no cap; Telegram usually caps anyway).
    audience_scan_max_users: int = 0

    # --- Invites (PHASE 6) ---
    # Spacing between invites for a single account (seconds), randomized.
    invite_delay_min: float = 20.0
    invite_delay_max: float = 60.0
    # Tasks processed per scheduler tick (keeps memory/CPU low on weak machines).
    invite_batch_size: int = 5
    # Default caps when a job does not specify its own (0 = no cap).
    invite_max_total: int = 0
    invite_max_per_account: int = 0

    # --- Scheduler ---
    scheduler_enabled: bool = True
    scheduler_timezone: str = "UTC"

    # --- Backup / Restore (PHASE 10) ---
    # Where generated backups are written (git-ignored, outside the DB).
    backup_dir: str = "./backups"
    # How many recent backups to keep; older ones are pruned (0 = keep all).
    backup_retention: int = 20
    # Include the (git-ignored) MTProto session files in a backup. Off by default
    # because session files grant full account access; handle them separately.
    backup_include_sessions: bool = False

    # --- Tiny AI (PHASE 7) ---
    # Master switch. Off by default: the system works on rules alone.
    ai_enabled: bool = False
    # Inference backend: "llama_cpp" (real, optional) or "fake" (offline/tests).
    # Empty = auto (fake when offline_mode, else llama_cpp).
    ai_backend: str = ""
    # Path to a user-provided .gguf model. Never committed; never auto-downloaded.
    ai_model_path: str = ""
    # Directory scanned for available .gguf models (portable: <root>/models).
    models_dir: str = "./models"
    # CPU threads for inference. 2 is safe on very weak machines.
    ai_model_threads: int = 2
    # Context window (tokens). Small keeps RAM low.
    ai_context_size: int = 2048
    # Sampling temperature. Low = more deterministic classification.
    ai_temperature: float = 0.1
    # Max tokens generated per classification (the JSON answer is tiny).
    ai_max_tokens: int = 128
    # Hard timeout for one inference, in seconds.
    ai_timeout_seconds: float = 30.0
    # Keep the model resident between calls (faster, uses RAM). Off by default
    # so a weak PC does not hold a model in memory while idle.
    ai_keep_loaded: bool = False
    # Rules confidence at/above which the AI is not consulted (fast path).
    ai_rules_threshold: float = 0.55
    # AI confidence at/above which the AI result is accepted over rules.
    ai_confidence_threshold: float = 0.6
    # How many recent AI inference records to keep for diagnostics (0 = none).
    ai_history_limit: int = 200

    # --- Telegram Mini App (PHASE 9) ---
    # Master switch. Off by default: the local Web UI is the primary interface.
    miniapp_enabled: bool = False
    # Max age (seconds) of Telegram initData before it is rejected as stale.
    miniapp_initdata_max_age: int = 86400
    # Lifetime (seconds) of a signed Mini App session cookie.
    miniapp_session_ttl: int = 86400
    # Public HTTPS URL the Mini App is served from (e.g. https://example.com).
    # Empty for local-only installs; shown to the owner so they can register it
    # as the bot's Web App URL in BotFather.
    miniapp_public_url: str = ""

    # --- Logging ---
    log_level: str = "INFO"
    log_dir: str = "./logs"

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

    def resolve_exports_dir(self) -> Path:
        p = Path(self.exports_dir)
        return p if p.is_absolute() else (paths.project_root() / p).resolve()

    def resolve_models_dir(self) -> Path:
        p = Path(self.models_dir)
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
