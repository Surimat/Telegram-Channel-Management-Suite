"""Permission probe service tests (post-1.0 hardening).

Exercises the real service + fake provider, so no Telegram account is needed.
Covers every machine status and verifies secrets never leak.
"""

from __future__ import annotations

import pytest

from backend.app.db.session import init_models, session_scope
from backend.app.providers.errors import (
    ChatAdminRequiredError,
    EntityNotFoundError,
    FloodWaitError,
    PrivacyRestrictedError,
    SessionInvalidError,
)
from backend.app.providers.fake_session import (
    FakeAuthScenario,
    FakePermissionScenario,
    FakeSessionProvider,
)
from backend.app.services.permission_service import (
    STATUS_ADMIN_REQUIRED,
    STATUS_AUTH_REQUIRED,
    STATUS_FLOOD_WAIT,
    STATUS_NO_ACCESS,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_PRIVACY_RESTRICTED,
    PermissionService,
    PermissionServiceError,
)


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


def factory_for(provider: FakeSessionProvider):
    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        provider._session_path = session_path
        return provider

    return _factory


async def _make_account(svc) -> str:
    from backend.app.providers.fake_session import DEFAULT_CODE

    started = await svc.start_auth(api_id="1", api_hash="h", phone="+79990000000")
    await svc.submit_code(started.account_id, DEFAULT_CODE)
    return started.account_id


async def test_ok_when_invites_allowed() -> None:
    provider = FakeSessionProvider(permission=FakePermissionScenario(can_invite=True))
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        result = await svc.check(account_id, "@chan")
        assert result.status == STATUS_OK
        assert result.can_invite is True
        assert result.channel_found is True
        assert result.check_id


async def test_partial_when_cannot_invite() -> None:
    provider = FakeSessionProvider(
        permission=FakePermissionScenario(can_invite=False, participants_hidden=False)
    )
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        result = await svc.check(account_id, "@chan")
        assert result.status == STATUS_PARTIAL
        assert result.can_read_participants is True
        assert result.can_invite is False
        assert result.how_to_fix


async def test_privacy_restricted_when_members_hidden() -> None:
    provider = FakeSessionProvider(
        permission=FakePermissionScenario(can_invite=False, participants_hidden=True)
    )
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        result = await svc.check(account_id, "@chan")
        assert result.status == STATUS_PRIVACY_RESTRICTED
        assert result.can_read_participants is False


async def test_not_found_maps_to_no_access() -> None:
    provider = FakeSessionProvider(
        permission=FakePermissionScenario(resolve_error=EntityNotFoundError("no such channel"))
    )
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        result = await svc.check(account_id, "@missing")
        assert result.status == STATUS_NO_ACCESS


async def test_flood_wait_reported_with_retry_after() -> None:
    provider = FakeSessionProvider(
        permission=FakePermissionScenario(
            participants_error=FloodWaitError(42)
        )
    )
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        result = await svc.check(account_id, "@chan")
        assert result.status == STATUS_FLOOD_WAIT
        assert result.retry_after == 42


async def test_auth_required_when_session_invalid() -> None:
    provider = FakeSessionProvider(
        permission=FakePermissionScenario(resolve_error=SessionInvalidError("logged out"))
    )
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        result = await svc.check(account_id, "@chan")
        assert result.status == STATUS_AUTH_REQUIRED


async def test_admin_required_status() -> None:
    provider = FakeSessionProvider(
        permission=FakePermissionScenario(resolve_error=ChatAdminRequiredError("admin only"))
    )
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        result = await svc.check(account_id, "@chan")
        assert result.status == STATUS_ADMIN_REQUIRED


async def test_privacy_error_status() -> None:
    provider = FakeSessionProvider(
        permission=FakePermissionScenario(
            resolve_error=PrivacyRestrictedError("private")
        )
    )
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        result = await svc.check(account_id, "@chan")
        assert result.status == STATUS_PRIVACY_RESTRICTED


async def test_empty_target_rejected() -> None:
    provider = FakeSessionProvider()
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        with pytest.raises(PermissionServiceError):
            await svc.check("nope", "   ")


async def test_unknown_account_rejected() -> None:
    provider = FakeSessionProvider()
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        with pytest.raises(PermissionServiceError) as exc:
            await svc.check("missing-account", "@chan")
        assert exc.value.status_code == 404


async def test_history_and_latest_persisted() -> None:
    provider = FakeSessionProvider(permission=FakePermissionScenario(can_invite=True))
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        await svc.check(account_id, "@chan")
        latest = await svc.latest()
        history = await svc.history()
        assert latest is not None
        assert latest.status == STATUS_OK
        assert len(history) == 1


async def test_no_secret_material_in_result() -> None:
    """The result must never carry tokens, hashes or session contents."""
    provider = FakeSessionProvider(permission=FakePermissionScenario(can_invite=True))
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        result = await svc.check(account_id, "@chan")
        blob = repr(result).lower()
        # No secret material: only the boolean "session_ok" flag may appear.
        assert "api_hash" not in blob
        assert "password" not in blob
        assert "token" not in blob
        assert "phone" not in blob
        assert "enc:" not in blob


async def test_unauthorized_provider_reports_auth_required() -> None:
    provider = FakeSessionProvider(
        scenario=FakeAuthScenario(authorized=False),
        permission=FakePermissionScenario(),
    )
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        from backend.app.core.config import get_settings
        from backend.app.core.security import seal_secret
        from backend.app.db.models.session import SessionStatus, UserSession

        settings = get_settings()
        account = UserSession(
            display_name="Test",
            phone_masked="+7999***0000",
            api_id="1",
            api_hash_encrypted=seal_secret("h", settings),
            session_ref="sessions/test.session",
            status=SessionStatus.AUTH_REQUIRED,
        )
        db.add(account)
        await db.flush()
        result = await svc.check(account.id, "@chan")
        assert result.status == STATUS_AUTH_REQUIRED


async def test_registry_channel_supplies_target_and_is_recorded() -> None:
    """A probe can target a registered channel instead of typing it (D-052)."""
    from backend.app.db.models.channel import Channel
    from backend.app.db.repositories.channels import ChannelRepository

    provider = FakeSessionProvider(permission=FakePermissionScenario(can_invite=True))
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        channel = await ChannelRepository(db).add(
            Channel(reference="@registered", title="Registered", username="registered")
        )
        result = await svc.check(account_id, "", registry_channel_id=channel.id)
        assert result.status == STATUS_OK
        assert result.target == "@registered"
        assert result.registry_channel_id == channel.id
        channel_id = channel.id

    # The link survives a reload (history is per-channel retrievable).
    async with session_scope() as db:
        latest = await PermissionService(db).latest()
        assert latest is not None
        assert latest.registry_channel_id == channel_id


async def test_registry_channel_missing_is_a_friendly_error() -> None:
    provider = FakeSessionProvider(permission=FakePermissionScenario())
    async with session_scope() as db:
        svc = PermissionService(db, session_provider_factory=factory_for(provider))
        account_id = await _make_account(svc._session_service())
        with pytest.raises(PermissionServiceError) as excinfo:
            await svc.check(account_id, "", registry_channel_id="does-not-exist")
        assert excinfo.value.status_code == 404
