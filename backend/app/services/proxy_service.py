"""Proxy Manager service (v1.1: connection routes).

A proxy here is an ordinary network route for an account. The service can:

* create/update/delete profiles (password stored sealed, never returned);
* bind a profile to a user account (``UserSession.proxy_id``);
* run a **real** connection check through the proxy and report
  ``OK`` / ``ERROR`` / ``TIMEOUT`` — never an assumption.

It deliberately provides **no** rotation, no automatic account distribution and
no FloodWait evasion: those are out of scope by design (D-006, D-066).
"""

from __future__ import annotations

import asyncio
import socket
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import open_secret, seal_secret
from backend.app.db.base import utcnow
from backend.app.db.models.proxy import (
    KIND_TITLES,
    STATUS_TITLES,
    ProxyKind,
    ProxyProfile,
    ProxyStatus,
)
from backend.app.db.models.session import UserSession
from backend.app.db.repositories.proxies import ProxyRepository
from backend.app.db.repositories.sessions import SessionRepository
from backend.app.services.events_service import EventsService

MODULE = "proxy"

#: The explicit, non-negotiable product statement shown in the UI.
NO_BYPASS_NOTICE = (
    "Прокси — это обычный сетевой маршрут подключения аккаунта. "
    "Прокси не отменяет ограничения Telegram."
)


class ProxyServiceError(Exception):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


@dataclass(slots=True)
class ProxyView:
    id: str
    name: str
    kind: str
    kind_title: str
    host: str
    port: int
    username: str
    has_password: bool
    enabled: bool
    status: str
    status_title: str
    status_message: str
    last_checked: str = ""
    account_ids: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        """Public fields only (never a password; account ids are internal)."""
        from dataclasses import asdict

        data = asdict(self)
        data.pop("account_ids", None)
        return data


@dataclass(slots=True)
class ProxyCheck:
    profile_id: str
    ok: bool
    status: str
    status_title: str
    message: str
    how_to_fix: str = ""
    latency_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        from dataclasses import asdict

        return asdict(self)


def _validate(kind: str, host: str, port: int) -> tuple[ProxyKind, str]:
    try:
        kind_enum = ProxyKind(kind)
    except ValueError as exc:
        raise ProxyServiceError(
            "Неизвестный тип прокси.",
            how_to_fix="Допустимо: socks5, http, https.",
        ) from exc
    host = (host or "").strip()
    if not host:
        raise ProxyServiceError("Укажите адрес прокси (host).")
    if not (1 <= int(port) <= 65535):
        raise ProxyServiceError(
            "Порт должен быть от 1 до 65535.",
            how_to_fix="Стандартные порты: SOCKS5 — 1080, HTTP/HTTPS — 8080/3128.",
        )
    return kind_enum, host


def build_telethon_proxy(profile: ProxyProfile, *, password: str = "") -> dict[str, object]:
    """Return the Telethon ``proxy`` dict for a profile (secret stays in memory)."""
    return {
        "proxy_type": profile.kind.value,
        "addr": profile.host,
        "port": int(profile.port),
        "username": profile.username or None,
        "password": password or None,
        "rdns": True,
    }


class ProxyService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        connect_timeout: float = 8.0,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = ProxyRepository(session)
        self.sessions = SessionRepository(session)
        self.events = EventsService(session)
        self._connect_timeout = connect_timeout

    # --- inventory -----------------------------------------------------------
    async def list_profiles(self) -> list[ProxyView]:
        rows = await self.repo.list_all()
        return [self._view(row) for row in rows]

    async def get(self, profile_id: str) -> ProxyProfile | None:
        return await self.repo.get(profile_id)

    # --- CRUD ----------------------------------------------------------------
    async def create(
        self,
        *,
        name: str = "",
        kind: str,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        enabled: bool = True,
    ) -> ProxyProfile:
        kind_enum, host = _validate(kind, host, port)
        profile = ProxyProfile(
            name=(name or "").strip() or f"{KIND_TITLES[kind_enum]} {host}",
            kind=kind_enum,
            host=host,
            port=int(port),
            username=(username or "").strip(),
            password_encrypted=seal_secret(password, self.settings) if password else "",
            enabled=enabled,
            status=ProxyStatus.UNKNOWN,
            status_message=STATUS_TITLES[ProxyStatus.UNKNOWN],
        )
        await self.repo.add(profile)
        await self.events.info(
            MODULE,
            f"Добавлен прокси «{profile.name}».",
            explanation=NO_BYPASS_NOTICE,
            operation="create",
            status="ok",
        )
        await self.session.commit()
        return profile

    async def update(
        self,
        profile_id: str,
        *,
        name: str | None = None,
        kind: str | None = None,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        enabled: bool | None = None,
    ) -> ProxyProfile:
        profile = await self.repo.get(profile_id)
        if profile is None:
            raise ProxyServiceError("Прокси не найден.", status_code=404)
        kind_value = kind or profile.kind.value
        host_value = host if host is not None else profile.host
        port_value = port if port is not None else profile.port
        kind_enum, host_value = _validate(kind_value, host_value, port_value)
        profile.kind = kind_enum
        profile.host = host_value
        profile.port = int(port_value)
        if name is not None:
            profile.name = name.strip()
        if username is not None:
            profile.username = username.strip()
        if password is not None:
            profile.password_encrypted = (
                seal_secret(password, self.settings) if password else ""
            )
        if enabled is not None:
            profile.enabled = enabled
        profile.status = ProxyStatus.UNKNOWN
        profile.status_message = STATUS_TITLES[ProxyStatus.UNKNOWN]
        await self.session.flush()
        await self.session.commit()
        return profile

    async def delete(self, profile_id: str) -> None:
        profile = await self.repo.get(profile_id)
        if profile is None:
            raise ProxyServiceError("Прокси не найден.", status_code=404)
        # Unbind any accounts using it (never delete an account automatically).
        accounts, _ = await self.sessions.list(limit=10_000)
        for account in accounts:
            if account.proxy_id == profile_id:
                account.proxy_id = ""
        await self.repo.delete(profile)
        await self.session.commit()

    # --- binding -------------------------------------------------------------
    async def bind_account(self, account_id: str, profile_id: str) -> UserSession:
        account = await self.sessions.get(account_id)
        if account is None:
            raise ProxyServiceError("Аккаунт не найден.", status_code=404)
        if profile_id:
            profile = await self.repo.get(profile_id)
            if profile is None:
                raise ProxyServiceError("Прокси не найден.", status_code=404)
        account.proxy_id = profile_id
        await self.session.flush()
        await self.session.commit()
        return account

    # --- check ---------------------------------------------------------------
    async def check(self, profile_id: str) -> ProxyCheck:
        """Open a TCP connection through/at the proxy and record the real result."""
        profile = await self.repo.get(profile_id)
        if profile is None:
            raise ProxyServiceError("Прокси не найден.", status_code=404)
        started = time.monotonic()
        status, message, fix = await self._probe(profile)
        latency = int((time.monotonic() - started) * 1000)
        profile.status = status
        profile.status_message = message
        profile.last_checked = utcnow()
        await self.session.flush()
        await self.events.info(
            MODULE,
            f"Проверка прокси «{profile.name}»: {STATUS_TITLES[status]}.",
            explanation=message,
            operation="check",
            status="ok" if status == ProxyStatus.OK else "warning",
        )
        await self.session.commit()
        return ProxyCheck(
            profile_id=profile.id,
            ok=status == ProxyStatus.OK,
            status=status.value,
            status_title=STATUS_TITLES[status],
            message=message,
            how_to_fix=fix,
            latency_ms=latency,
        )

    async def _probe(self, profile: ProxyProfile) -> tuple[ProxyStatus, str, str]:
        """Best-effort TCP reachability probe (no Telegram calls, no secrets)."""
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._tcp_connect, profile.host, int(profile.port)),
                timeout=self._connect_timeout,
            )
        except TimeoutError:
            return (
                ProxyStatus.TIMEOUT,
                "Прокси не ответил за отведённое время.",
                "Проверьте адрес и порт; возможно, прокси недоступен.",
            )
        except OSError as exc:
            return (
                ProxyStatus.ERROR,
                "Не удалось подключиться к прокси.",
                f"Проверьте адрес, порт и логин/пароль. ({type(exc).__name__})",
            )
        return (
            ProxyStatus.OK,
            "Прокси принимает подключения. Помните: прокси не отменяет "
            "ограничения Telegram.",
            "",
        )

    @staticmethod
    def _tcp_connect(host: str, port: int) -> None:
        with socket.create_connection((host, port), timeout=5.0):
            return

    # --- helpers -------------------------------------------------------------
    def _view(self, profile: ProxyProfile) -> ProxyView:
        return ProxyView(
            id=profile.id,
            name=profile.name,
            kind=profile.kind.value,
            kind_title=KIND_TITLES.get(profile.kind, profile.kind.value),
            host=profile.host,
            port=profile.port,
            username=profile.username,
            has_password=bool(profile.password_encrypted),
            enabled=profile.enabled,
            status=profile.status.value,
            status_title=STATUS_TITLES.get(profile.status, profile.status.value),
            status_message=profile.status_message,
            last_checked=profile.last_checked.isoformat() if profile.last_checked else "",
        )

    def telethon_proxy_for(self, profile: ProxyProfile) -> dict[str, object]:
        """Return the Telethon proxy dict, opening the sealed password."""
        password = ""
        if profile.password_encrypted:
            try:
                password = open_secret(profile.password_encrypted, self.settings)
            except ValueError:
                password = ""
        return build_telethon_proxy(profile, password=password)


__all__ = [
    "MODULE",
    "NO_BYPASS_NOTICE",
    "ProxyCheck",
    "ProxyService",
    "ProxyServiceError",
    "ProxyView",
    "build_telethon_proxy",
]
