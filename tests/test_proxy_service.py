"""v1.1 proxy (connection route) service tests.

The reachability check opens a real TCP connection, so the tests use a local
listening socket (no external network). Secrets are asserted to stay sealed and
to never be returned by a view.
"""

from __future__ import annotations

import socket

import pytest

from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.db.session import init_models, session_scope
from backend.app.services.proxy_service import (
    NO_BYPASS_NOTICE,
    ProxyService,
    ProxyServiceError,
)


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


def _listening_socket() -> tuple[socket.socket, int]:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    return srv, srv.getsockname()[1]


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def test_create_seals_password_and_never_exposes_it() -> None:
    async with session_scope() as db:
        svc = ProxyService(db)
        profile = await svc.create(
            name="Домашний", kind="socks5", host="127.0.0.1", port=1080, password="s3cret"
        )
        assert profile.password_encrypted.startswith("enc:")
        assert "s3cret" not in profile.password_encrypted
        view = svc._view(profile)
        assert view.has_password is True
        assert not hasattr(view, "password")
        # The Telethon dict opens the sealed password for the real connection.
        proxy = svc.telethon_proxy_for(profile)
        assert proxy["password"] == "s3cret"
        assert proxy["addr"] == "127.0.0.1"


async def test_create_validates_kind_and_port() -> None:
    async with session_scope() as db:
        svc = ProxyService(db)
        with pytest.raises(ProxyServiceError):
            await svc.create(kind="ftp", host="h", port=1)
        with pytest.raises(ProxyServiceError):
            await svc.create(kind="socks5", host="", port=1)
        with pytest.raises(ProxyServiceError):
            await svc.create(kind="socks5", host="h", port=0)


async def test_update_resets_status_and_password() -> None:
    async with session_scope() as db:
        svc = ProxyService(db)
        profile = await svc.create(kind="http", host="10.0.0.1", port=8080, password="old")
        updated = await svc.update(profile.id, name="New", host="10.0.0.2", password="")
        assert updated.name == "New"
        assert updated.host == "10.0.0.2"
        assert updated.password_encrypted == ""
        assert svc._view(updated).has_password is False


async def test_bind_and_unbind_account() -> None:
    async with session_scope() as db:
        db.add(
            UserSession(
                telegram_user_id=1, username="u",
                status=SessionStatus.ONLINE, api_id="1",
            )
        )
        await db.flush()
        svc = ProxyService(db)
        profile = await svc.create(kind="socks5", host="127.0.0.1", port=1080)
        accounts, _ = await svc.sessions.list()
        account_id = accounts[0].id
        bound = await svc.bind_account(account_id, profile.id)
        assert bound.proxy_id == profile.id
        unbound = await svc.bind_account(account_id, "")
        assert unbound.proxy_id == ""


async def test_delete_unbinds_accounts_without_deleting_them() -> None:
    async with session_scope() as db:
        db.add(
            UserSession(
                telegram_user_id=2, username="v",
                status=SessionStatus.ONLINE, api_id="1",
            )
        )
        await db.flush()
        svc = ProxyService(db)
        profile = await svc.create(kind="socks5", host="127.0.0.1", port=1080)
        account = (await svc.sessions.list())[0][0]
        await svc.bind_account(account.id, profile.id)
        await svc.delete(profile.id)
        refreshed = await svc.sessions.get(account.id)
        assert refreshed is not None  # the account is never removed automatically
        assert refreshed.proxy_id == ""
        assert await svc.get(profile.id) is None


async def test_check_ok_against_listening_socket() -> None:
    srv, port = _listening_socket()
    try:
        async with session_scope() as db:
            svc = ProxyService(db)
            profile = await svc.create(kind="socks5", host="127.0.0.1", port=port)
            result = await svc.check(profile.id)
            assert result.ok is True
            assert result.status == "ok"
            # The stored profile reflects the real result.
            assert (await svc.get(profile.id)).status.value == "ok"
    finally:
        srv.close()


async def test_check_error_against_closed_port() -> None:
    async with session_scope() as db:
        svc = ProxyService(db)
        profile = await svc.create(kind="socks5", host="127.0.0.1", port=_free_port())
        result = await svc.check(profile.id)
        assert result.ok is False
        assert result.status in {"error", "timeout"}
        assert result.how_to_fix


def test_no_bypass_notice_is_explicit() -> None:
    assert "не отменяет" in NO_BYPASS_NOTICE
