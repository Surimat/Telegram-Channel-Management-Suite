"""Channel Registry tests (hardening: one shared channel identity).

Exercises the real service + API against the deterministic fake session provider,
so no Telegram account or network is needed. Covers reference normalization,
add → verify → connect modules → default, duplicate protection, and the invite
integration (choosing a channel supplies the target).
"""

from __future__ import annotations

import pytest

from backend.app.db.models.channel import ChannelStatus
from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.db.session import init_models, session_scope
from backend.app.services.channel_service import (
    ChannelService,
    ChannelServiceError,
    normalize_reference,
)


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


async def _seed_account() -> str:
    from backend.app.db.base import new_id

    account = UserSession(
        id=new_id(),
        telegram_user_id=1000001,
        username="fake_user",
        display_name="Fake User",
        status=SessionStatus.ONLINE,
        enabled=True,
        api_id="1",
    )
    async with session_scope() as session:
        session.add(account)
    return account.id


def _factory_for(provider):
    def _factory(*, api_id="", api_hash="", session_path=None, provider_name="auto", settings=None):
        return provider

    return _factory


# --- normalization ----------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@mychannel", "@mychannel"),
        ("mychannel", "@mychannel"),
        ("https://t.me/mychannel", "@mychannel"),
        ("http://t.me/mychannel/", "@mychannel"),
        ("t.me/mychannel", "@mychannel"),
        ("-1001234567890", "-1001234567890"),
        ("  @chan  ", "@chan"),
        ("", ""),
    ],
)
def test_normalize_reference(raw: str, expected: str) -> None:
    assert normalize_reference(raw) == expected


# --- service ----------------------------------------------------------------
async def test_add_verify_default_and_modules() -> None:
    from backend.app.providers.fake_session import FakePermissionScenario, FakeSessionProvider

    provider = FakeSessionProvider(permission=FakePermissionScenario(can_invite=True))
    account_id = await _seed_account()
    async with session_scope() as db:
        svc = ChannelService(db, session_provider_factory=_factory_for(provider))
        channel = await svc.add("https://t.me/faketest")
        # Normalized reference, first channel becomes the default.
        assert channel.reference == "@faketest"
        assert channel.is_default is True

        result = await svc.verify(channel.id, account_id)
        assert result.status == "ok"
        assert result.title == "Fake Channel"
        refreshed = await svc.get(channel.id)
        assert refreshed is not None
        assert refreshed.status == ChannelStatus.VERIFIED
        assert refreshed.username == "fakechannel"
        assert refreshed.telegram_id is not None
        assert refreshed.participants_count == 1234

        await svc.set_modules(channel.id, {"reactions": True, "invites": True})
        modules = await svc.modules_of(refreshed)
        assert modules["reactions"] is True
        assert modules["invites"] is True
        assert modules["audience"] is False


async def test_duplicate_reference_rejected() -> None:
    async with session_scope() as db:
        svc = ChannelService(db)
        await svc.add("@dupchan")
        with pytest.raises(ChannelServiceError):
            await svc.add("https://t.me/dupchan")


async def test_default_promoted_on_delete() -> None:
    async with session_scope() as db:
        svc = ChannelService(db)
        first = await svc.add("@first")
        second = await svc.add("@second", make_default=True)
        assert second.is_default is True
        assert first.is_default is False

        await svc.delete(second.id)
        remaining, _ = await svc.list_channels()
        assert len(remaining) == 1
        assert remaining[0].id == first.id
        assert remaining[0].is_default is True


async def test_verify_records_error_status() -> None:
    from backend.app.providers.errors import EntityNotFoundError
    from backend.app.providers.fake_session import FakePermissionScenario, FakeSessionProvider

    provider = FakeSessionProvider(
        permission=FakePermissionScenario(resolve_error=EntityNotFoundError("no"))
    )
    account_id = await _seed_account()
    async with session_scope() as db:
        svc = ChannelService(db, session_provider_factory=_factory_for(provider))
        channel = await svc.add("@missing")
        result = await svc.verify(channel.id, account_id)
        assert result.status == "no_access"
        refreshed = await svc.get(channel.id)
        assert refreshed is not None
        assert refreshed.status == ChannelStatus.ERROR


# --- API --------------------------------------------------------------------
async def test_api_add_verify_list_summary(channel_client) -> None:
    account_id = await _seed_account()
    resp = await channel_client.post("/api/v1/channels", json={"reference": "t.me/api_chan"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["reference"] == "@api_chan"
    assert body["is_default"] is True
    channel_id = body["id"]

    resp = await channel_client.post(
        f"/api/v1/channels/{channel_id}/verify", json={"account_id": account_id}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"

    resp = await channel_client.post(
        f"/api/v1/channels/{channel_id}/modules", json={"modules": {"reactions": True}}
    )
    assert resp.status_code == 200
    assert resp.json()["modules"]["reactions"] is True

    resp = await channel_client.get("/api/v1/channels/summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total"] == 1
    assert summary["verified"] == 1
    assert summary["default_channel_id"] == channel_id

    resp = await channel_client.get("/api/v1/channels", params={"search": "api"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


async def test_api_duplicate_returns_friendly_error(channel_client) -> None:
    created = await channel_client.post("/api/v1/channels", json={"reference": "@one"})
    assert created.status_code == 201
    resp = await channel_client.post("/api/v1/channels", json={"reference": "@one"})
    assert resp.status_code == 400
    assert "уже добавлен" in resp.json()["error"]["message"].lower()


async def test_api_delete_returns_204(channel_client) -> None:
    created = (await channel_client.post("/api/v1/channels", json={"reference": "@kill"})).json()
    resp = await channel_client.delete(f"/api/v1/channels/{created['id']}")
    assert resp.status_code == 204
    assert (await channel_client.get(f"/api/v1/channels/{created['id']}")).status_code == 404


async def test_invite_uses_registry_channel(invite_client) -> None:
    """Creating an invite job with a channel_id resolves the target from it."""
    created = (
        await invite_client.post("/api/v1/channels", json={"reference": "@target"})
    ).json()

    resp = await invite_client.post(
        "/api/v1/invites",
        json={"channel_id": created["id"], "dry_run": True},
    )
    assert resp.status_code == 201, resp.text
    job = resp.json()
    assert job["channel_id"] == created["id"]
    assert job["target"] == "@target"
    assert job["target_title"] == "@target"


async def test_invite_rejects_unknown_channel(invite_client) -> None:
    resp = await invite_client.post(
        "/api/v1/invites",
        json={"channel_id": "does-not-exist", "dry_run": True},
    )
    assert resp.status_code == 404
