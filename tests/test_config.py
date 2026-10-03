"""Configuration tests: defaults, validation, redaction safety."""

from __future__ import annotations

from backend.app.core.config import Settings, secret_values


def test_defaults_are_sane() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8000
    assert settings.app_language == "ru"
    assert settings.ai_enabled is False


def test_scheduler_enabled_default() -> None:
    # Default is True when the environment does not override it.
    settings = Settings(_env_file=None, scheduler_enabled=True)
    assert settings.scheduler_enabled is True


def test_cors_origins_parsing() -> None:
    settings = Settings(_env_file=None, app_cors_origins="http://a, http://b ,")
    assert settings.cors_origins == ["http://a", "http://b"]


def test_admin_ids_parsing() -> None:
    settings = Settings(_env_file=None, manager_bot_admin_ids="123, 456 ,x, 789")
    assert settings.admin_ids == [123, 456, 789]


def test_invalid_log_level_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        Settings(_env_file=None, log_level="LOUD")


def test_secret_values_masks_and_collects() -> None:
    settings = Settings(
        _env_file=None,
        app_secret_key="super-secret-key-value",
        manager_bot_token="123:ABC",
        telegram_api_hash="hashvalue",
        telegram_api_id="999",
    )
    values = secret_values(settings)
    assert "super-secret-key-value" in values
    assert "123:ABC" in values
    assert "hashvalue" in values
    assert "999" in values


def test_secret_not_in_repr() -> None:
    settings = Settings(_env_file=None, manager_bot_token="123:SECRETXYZ")
    assert "SECRETXYZ" not in repr(settings)
