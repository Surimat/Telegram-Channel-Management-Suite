"""Server-side verification of Telegram Mini App ``initData``.

Per Telegram's Mini App documentation, ``initData`` is a URL-encoded query string
signed with an HMAC-SHA256 over the *sorted* key/value pairs, using
``HMAC_SHA256(bot_token, "WebAppData")`` as the secret key. We verify the
signature in constant time, reject stale payloads, and parse the ``user`` field.

Security notes (see docs/SECURITY.md):

* The raw ``initData`` and the bot token are never logged, stored, or returned.
* A tampered or expired payload raises :class:`MiniAppAuthError` with a friendly
  message; the technical reason stays in the exception ``reason`` for the log.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class MiniAppAuthError(Exception):
    """Raised when ``initData`` cannot be trusted.

    ``reason`` is a short machine-readable code for logging/diagnostics; it is
    never shown to the user verbatim.
    """

    def __init__(self, reason: str, message: str = "", *, hint: str = "") -> None:
        super().__init__(message or "Не удалось проверить данные Telegram.")
        self.reason = reason
        self.message = message or "Не удалось проверить данные Telegram."
        self.hint = hint or "Откройте мини-приложение заново из Telegram."


@dataclass(frozen=True)
class MiniAppUser:
    """The Telegram user described by a verified ``initData`` payload."""

    id: int
    first_name: str = ""
    last_name: str = ""
    username: str = ""
    language_code: str = ""
    is_premium: bool = False
    allows_write_to_pm: bool = False
    photo_url: str = ""

    @property
    def display_name(self) -> str:
        full = " ".join(p for p in (self.first_name, self.last_name) if p).strip()
        return full or (f"@{self.username}" if self.username else str(self.id))


def _secret_key(bot_token: str) -> bytes:
    """Derive the signing key from the manager bot token (never logged)."""
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def _data_check_string(pairs: list[tuple[str, str]]) -> str:
    """Build the canonical ``key=value`` string Telegram signs.

    Keys are sorted; the ``hash`` field itself is excluded.
    """
    filtered = sorted((k, v) for k, v in pairs if k != "hash")
    return "\n".join(f"{k}={v}" for k, v in filtered)


def verify_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age: int = 86400,
    now: float | None = None,
) -> MiniAppUser:
    """Verify a Mini App ``initData`` string and return the Telegram user.

    Raises :class:`MiniAppAuthError` when the payload is missing, unsigned,
    tampered, expired, or has no parseable user.
    """
    if not init_data:
        raise MiniAppAuthError("missing", "Telegram не передал данные для входа.")
    if not bot_token:
        raise MiniAppAuthError(
            "no_token",
            "Управляющий бот не настроен, поэтому вход из Telegram недоступен.",
            hint="Подключите управляющего бота в разделе «Боты».",
        )

    pairs = parse_qsl(init_data, keep_blank_values=True)
    if not pairs:
        raise MiniAppAuthError("malformed", "Данные для входа повреждены.")

    received_hash = next((v for k, v in pairs if k == "hash"), "")
    if not received_hash:
        raise MiniAppAuthError("no_hash", "Данные для входа не подписаны.")

    data_check_string = _data_check_string(pairs)
    expected = hmac.new(
        _secret_key(bot_token), data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise MiniAppAuthError(
            "bad_signature",
            "Не удалось подтвердить, что данные пришли из Telegram.",
        )

    auth_date_raw = next((v for k, v in pairs if k == "auth_date"), "")
    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError):
        raise MiniAppAuthError("no_auth_date", "В данных для входа нет времени.") from None

    current = time.time() if now is None else now
    if max_age > 0 and current - auth_date > max_age:
        raise MiniAppAuthError(
            "expired",
            "Сессия входа устарела.",
            hint="Закройте и откройте мини-приложение заново.",
        )
    if auth_date - current > 60:
        raise MiniAppAuthError("future", "Время входа некорректно.")

    user_raw = next((v for k, v in pairs if k == "user"), "")
    if not user_raw:
        raise MiniAppAuthError("no_user", "Telegram не передал профиль пользователя.")
    try:
        payload = json.loads(user_raw)
        user_id = int(payload["id"])
    except (ValueError, KeyError, TypeError):
        raise MiniAppAuthError("bad_user", "Профиль пользователя повреждён.") from None

    return MiniAppUser(
        id=user_id,
        first_name=str(payload.get("first_name", "")),
        last_name=str(payload.get("last_name", "")),
        username=str(payload.get("username", "")),
        language_code=str(payload.get("language_code", "")),
        is_premium=bool(payload.get("is_premium", False)),
        allows_write_to_pm=bool(payload.get("allows_write_to_pm", False)),
        photo_url=str(payload.get("photo_url", "")),
    )
