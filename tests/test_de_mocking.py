"""Guards against a silent *fake* fallback outside the demo/test environments.

The deterministic fakes exist for the offline demo and the test suite (D-001).
They must never be selected silently anywhere else, or the panel would "work" on
fabricated data the owner cannot see. These tests pin that contract for the
provider registry and the AI backend registry.
"""

from __future__ import annotations

import pytest

from backend.app.ai.backends import (
    BACKEND_FAKE,
    build_backend,
    reject_fake_outside_allowed_envs,
)
from backend.app.ai.errors import AiError
from backend.app.core.config import Settings
from backend.app.providers.errors import ProviderConfigurationError
from backend.app.providers.registry import build_audience_provider, build_bot_provider


def _production() -> Settings:
    return Settings(app_env="production")


def test_bot_provider_fake_refused_in_production() -> None:
    with pytest.raises(ProviderConfigurationError):
        build_bot_provider("1:A", provider_name="fake", settings=_production())


def test_bot_provider_offline_fake_refused_in_production() -> None:
    with pytest.raises(ProviderConfigurationError):
        build_bot_provider("1:A", settings=Settings(app_env="production", offline_mode=True))


def test_bot_provider_fake_refused_in_development() -> None:
    # A bare default "development" is *not* an allowlisted environment: the very
    # hole the audit flagged is a deployment that forgets to set APP_ENV.
    with pytest.raises(ProviderConfigurationError):
        build_bot_provider("1:A", provider_name="fake", settings=Settings(app_env="development"))


def test_audience_provider_fake_refused_outside_demo_test() -> None:
    with pytest.raises(ProviderConfigurationError):
        build_audience_provider(None, provider_name="fake", settings=_production())


def test_ai_backend_fake_refused_outside_demo_test() -> None:
    with pytest.raises(AiError):
        build_backend(_production(), name=BACKEND_FAKE)
    with pytest.raises(AiError):
        build_backend(Settings(app_env="development"), name=BACKEND_FAKE)


def test_reject_fake_helper_allows_demo_and_test_only() -> None:
    for env in ("demo", "test"):
        reject_fake_outside_allowed_envs(Settings(app_env=env))
    for env in ("development", "production"):
        with pytest.raises(AiError):
            reject_fake_outside_allowed_envs(Settings(app_env=env))


def test_fake_allowed_in_demo_and_test_provider() -> None:
    from backend.app.providers.fake_bot import FakeTelegramBotProvider

    for env in ("demo", "test"):
        provider = build_bot_provider(
            "1:A", provider_name="fake", settings=Settings(app_env=env)
        )
        assert isinstance(provider, FakeTelegramBotProvider)
