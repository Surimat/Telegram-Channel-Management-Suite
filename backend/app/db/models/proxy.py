"""Network proxy profile model (v1.1: connection routes).

A proxy is an ordinary **network route** an account can use to reach Telegram —
nothing more. It is deliberately *not* a mechanism to bypass Telegram limits:
the suite never rotates proxies to evade FloodWait, privacy checks or identity
checks (D-006). The UI states this explicitly.

Only non-secret data is stored in plaintext (name, host, port, kind, username,
enabled). The password is stored **sealed** (Fernet, ``core.security``) and is
never returned by the API.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProxyKind(enum.StrEnum):
    """Supported proxy protocols."""

    SOCKS5 = "socks5"
    HTTP = "http"
    HTTPS = "https"


KIND_TITLES = {
    ProxyKind.SOCKS5: "SOCKS5",
    ProxyKind.HTTP: "HTTP",
    ProxyKind.HTTPS: "HTTPS",
}


class ProxyStatus(enum.StrEnum):
    """Result of the last connection check (never a guess)."""

    UNKNOWN = "unknown"   # never checked
    OK = "ok"             # reachable
    ERROR = "error"       # connection refused / auth failed
    TIMEOUT = "timeout"   # no answer in time


STATUS_TITLES = {
    ProxyStatus.UNKNOWN: "Не проверялся",
    ProxyStatus.OK: "Доступен",
    ProxyStatus.ERROR: "Ошибка подключения",
    ProxyStatus.TIMEOUT: "Нет ответа",
}


class ProxyProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "proxy_profiles"

    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    kind: Mapped[ProxyKind] = mapped_column(
        Enum(ProxyKind, name="proxy_kind"), default=ProxyKind.SOCKS5, nullable=False
    )
    host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=1080, nullable=False)
    username: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # Sealed password ("enc:..."). Never returned by the API.
    password_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    status: Mapped[ProxyStatus] = mapped_column(
        Enum(ProxyStatus, name="proxy_status"),
        default=ProxyStatus.UNKNOWN,
        nullable=False,
    )
    status_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ProxyProfile {self.kind}://{self.host}:{self.port} enabled={self.enabled}>"


__all__ = [
    "KIND_TITLES",
    "STATUS_TITLES",
    "ProxyKind",
    "ProxyProfile",
    "ProxyStatus",
]
