"""Unit tests for Mini App ``initData`` verification and session tokens.

No network and no real bot token: we sign payloads ourselves the same way
Telegram does, then assert the verifier accepts valid data and rejects tampering,
expiry, and malformed input.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from backend.app.miniapp.auth import MiniAppAuthError, verify_init_data
from backend.app.miniapp.sessions import (
    MiniAppSessionError,
    issue_session,
    verify_session,
)

BOT_TOKEN = "123456:TEST-TOKEN-not-a-real-secret"


def sign(fields: dict[str, object], bot_token: str = BOT_TOKEN) -> str:
    """Build a valid ``initData`` string exactly as Telegram would."""
    data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    payload = dict(fields)
    payload["hash"] = digest
    return urlencode(payload)


def base_fields(now: float | None = None) -> dict[str, object]:
    return {
        "auth_date": int(now if now is not None else time.time()),
        "query_id": "AAExample",
        "user": json.dumps(
            {
                "id": 42,
                "first_name": "Владелец",
                "last_name": "Канала",
                "username": "owner",
                "language_code": "ru",
            },
            ensure_ascii=False,
        ),
    }


def test_valid_init_data_returns_user() -> None:
    user = verify_init_data(sign(base_fields()), BOT_TOKEN)
    assert user.id == 42
    assert user.username == "owner"
    assert user.display_name == "Владелец Канала"


def test_tampered_user_is_rejected() -> None:
    init_data = sign(base_fields())
    tampered = init_data.replace("owner", "hacker")
    with pytest.raises(MiniAppAuthError) as exc:
        verify_init_data(tampered, BOT_TOKEN)
    assert exc.value.reason == "bad_signature"


def test_wrong_bot_token_is_rejected() -> None:
    with pytest.raises(MiniAppAuthError) as exc:
        verify_init_data(sign(base_fields()), "999:OTHER")
    assert exc.value.reason == "bad_signature"


def test_expired_init_data_is_rejected() -> None:
    old = time.time() - 100000
    with pytest.raises(MiniAppAuthError) as exc:
        verify_init_data(sign(base_fields(old)), BOT_TOKEN, max_age=3600)
    assert exc.value.reason == "expired"


def test_missing_hash_is_rejected() -> None:
    fields = base_fields()
    data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    with pytest.raises(MiniAppAuthError) as exc:
        verify_init_data(urlencode(fields) + "&hash=" + data_check[:8], BOT_TOKEN)
    assert exc.value.reason == "bad_signature"


def test_empty_init_data_is_rejected() -> None:
    with pytest.raises(MiniAppAuthError) as exc:
        verify_init_data("", BOT_TOKEN)
    assert exc.value.reason == "missing"


def test_missing_bot_token_is_reported() -> None:
    with pytest.raises(MiniAppAuthError) as exc:
        verify_init_data(sign(base_fields()), "")
    assert exc.value.reason == "no_token"


def test_missing_user_is_rejected() -> None:
    fields = base_fields()
    del fields["user"]
    with pytest.raises(MiniAppAuthError) as exc:
        verify_init_data(sign(fields), BOT_TOKEN)
    assert exc.value.reason == "no_user"


def test_session_roundtrip() -> None:
    token = issue_session(42, is_admin=True, ttl=3600)
    resolved = verify_session(token)
    assert resolved.telegram_id == 42
    assert resolved.is_admin is True


def test_session_expiry() -> None:
    token = issue_session(42, ttl=10, now=1000)
    with pytest.raises(MiniAppSessionError) as exc:
        verify_session(token, now=2000)
    assert exc.value.reason == "expired"


def test_session_tampering() -> None:
    token = issue_session(42, ttl=3600)
    body, _, signature = token.partition(".")
    with pytest.raises(MiniAppSessionError):
        verify_session(f"{body}.AAAA{signature[4:]}")


def test_session_missing() -> None:
    with pytest.raises(MiniAppSessionError) as exc:
        verify_session("")
    assert exc.value.reason == "missing"
