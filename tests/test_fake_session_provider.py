"""FakeSessionProvider + SessionService unit tests (PHASE 4).

Everything runs without Telegram: the fake provider drives the wizard, import,
health and error paths. No network, no real account.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.providers.errors import (
    AuthCodeExpiredError,
    AuthCodeInvalidError,
    FloodWaitError,
    PasswordInvalidError,
    SessionInvalidError,
)
from backend.app.providers.fake_session import (
    DEFAULT_CODE,
    DEFAULT_PASSWORD,
    FakeAuthScenario,
    FakeSessionProvider,
)
from backend.app.services.session_service import mask_phone, normalize_phone

# --- pure helpers ------------------------------------------------------------


def test_mask_phone_hides_middle() -> None:
    assert mask_phone("+79991234567") == "+7999***4567"
    assert "1234567" not in mask_phone("+79991234567")


def test_mask_phone_short_number() -> None:
    assert mask_phone("+799912") == "+79***12"
    assert mask_phone("") == ""


def test_normalize_phone() -> None:
    assert normalize_phone("+7 (999) 123-45-67") == "+79991234567"
    assert normalize_phone("89991234567") == "89991234567"
    assert normalize_phone("") == ""


# --- fake provider behaviour -------------------------------------------------


@pytest.mark.asyncio
async def test_fake_provider_health_ok_when_authorized() -> None:
    provider = FakeSessionProvider()
    identity = await provider.health()
    assert identity.id == 1000001
    assert identity.username == "fake_user"


@pytest.mark.asyncio
async def test_fake_provider_send_and_sign_in() -> None:
    scenario = FakeAuthScenario(authorized=False)
    provider = FakeSessionProvider(scenario=scenario)
    sent = await provider.send_code("+79991234567")
    assert sent.phone_code_hash.startswith("fake-hash:")
    result = await provider.sign_in("+79991234567", DEFAULT_CODE, sent.phone_code_hash)
    assert result.ok is True
    assert result.needs_password is False


@pytest.mark.asyncio
async def test_fake_provider_requires_password() -> None:
    scenario = FakeAuthScenario(authorized=False, requires_2fa=True)
    provider = FakeSessionProvider(scenario=scenario)
    sent = await provider.send_code("+79991234567")
    result = await provider.sign_in("+79991234567", DEFAULT_CODE, sent.phone_code_hash)
    assert result.needs_password is True
    done = await provider.sign_in_password(DEFAULT_PASSWORD)
    assert done.ok is True


@pytest.mark.asyncio
async def test_fake_provider_wrong_code_raises() -> None:
    scenario = FakeAuthScenario(authorized=False)
    provider = FakeSessionProvider(scenario=scenario)
    sent = await provider.send_code("+7999")
    with pytest.raises(AuthCodeInvalidError):
        await provider.sign_in("+7999", "00000", sent.phone_code_hash)


@pytest.mark.asyncio
async def test_fake_provider_expired_hash_raises() -> None:
    provider = FakeSessionProvider(scenario=FakeAuthScenario(authorized=False))
    with pytest.raises(AuthCodeExpiredError):
        await provider.sign_in("+7999", DEFAULT_CODE, "stale-hash")


@pytest.mark.asyncio
async def test_fake_provider_wrong_password_raises() -> None:
    provider = FakeSessionProvider(
        scenario=FakeAuthScenario(authorized=False, requires_2fa=True)
    )
    with pytest.raises(PasswordInvalidError):
        await provider.sign_in_password("nope")


@pytest.mark.asyncio
async def test_fake_provider_not_authorized_raises() -> None:
    provider = FakeSessionProvider(scenario=FakeAuthScenario(authorized=False))
    with pytest.raises(SessionInvalidError):
        await provider.health()


@pytest.mark.asyncio
async def test_fake_provider_injected_flood_wait() -> None:
    provider = FakeSessionProvider(
        scenario=FakeAuthScenario(send_code_error=FloodWaitError(42))
    )
    with pytest.raises(FloodWaitError) as exc:
        await provider.send_code("+7999")
    assert exc.value.retry_after == 42


@pytest.mark.asyncio
async def test_fake_provider_lazy_lifecycle() -> None:
    provider = FakeSessionProvider()
    assert provider.closed is True
    await provider.connect()
    assert provider.connected is True
    await provider.aclose()
    assert provider.closed is True


@pytest.mark.asyncio
async def test_fake_provider_export_creates_session_file(tmp_path: Path) -> None:
    provider = FakeSessionProvider(session_path=tmp_path / "abc.session")
    await provider.export_session()
    assert (tmp_path / "abc.session").is_file()
    assert provider.export_calls == 1
