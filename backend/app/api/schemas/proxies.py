"""Proxy API schemas (v1.1: connection routes).

The password is accepted on input and **never** returned. ``has_password``
indicates presence without revealing the value. The response also carries the
explicit non-bypass notice so the UI never implies proxies evade Telegram limits.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProxyOut(BaseModel):
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


class ProxyListOut(BaseModel):
    items: list[ProxyOut]
    notice: str


class ProxyIn(BaseModel):
    name: str = ""
    kind: str = "socks5"
    host: str
    port: int = 1080
    username: str = ""
    password: str = ""
    enabled: bool = True


class ProxyUpdateIn(BaseModel):
    name: str | None = None
    kind: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    enabled: bool | None = None


class ProxyCheckOut(BaseModel):
    profile_id: str
    ok: bool
    status: str
    status_title: str
    message: str
    how_to_fix: str = ""
    latency_ms: int = 0


class BindAccountIn(BaseModel):
    account_id: str
    profile_id: str = Field(default="", description="Пусто = прямое подключение.")


class BindResultOut(BaseModel):
    account_id: str
    proxy_id: str


__all__ = [
    "BindAccountIn",
    "BindResultOut",
    "ProxyCheckOut",
    "ProxyIn",
    "ProxyListOut",
    "ProxyOut",
    "ProxyUpdateIn",
]
