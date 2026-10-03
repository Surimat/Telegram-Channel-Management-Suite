"""Session Manager security tests (PHASE 4).

Verifies that credentials are sealed at rest, that registered secrets are masked
in log output, and that the API never returns secret material.
"""

from __future__ import annotations

import logging

from backend.app.core.config import get_settings
from backend.app.core.logging import register_secrets
from backend.app.core.security import open_secret, seal_secret
from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.db.repositories.sessions import SessionRepository
from backend.app.db.session import init_models, session_scope


def test_seal_and_open_roundtrip() -> None:
    sealed = seal_secret("my-secret-api-hash")
    assert sealed.startswith("enc:")
    assert "my-secret-api-hash" not in sealed
    assert open_secret(sealed) == "my-secret-api-hash"


def test_seal_empty_is_empty() -> None:
    assert seal_secret("") == ""
    assert open_secret("") == ""


def test_open_plain_value_passthrough() -> None:
    # Backward compatibility: unsealed values are returned unchanged.
    assert open_secret("plain-value") == "plain-value"


def test_log_redaction_masks_registered_secret() -> None:
    from backend.app.core.logging import RedactionFilter

    secret = "SUPER-SECRET-API-HASH-1234"
    register_secrets([secret])
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Using api_hash=%s for account",
        args=(secret,),
        exc_info=None,
    )
    assert RedactionFilter().filter(record) is True
    assert secret not in record.getMessage()
    assert "***REDACTED***" in record.getMessage()


async def test_model_stores_no_plaintext_credentials(tmp_path) -> None:
    await init_models()
    settings = get_settings()
    async with session_scope() as db:
        account = UserSession(
            api_id="123456",
            phone_masked="+7999***4567",
            phone_encrypted=seal_secret("+79991234567", settings),
            api_hash_encrypted=seal_secret("PLAIN-HASH", settings),
            session_ref="abc123",
            status=SessionStatus.DISCONNECTED,
        )
        await SessionRepository(db).add(account)
        await db.commit()
        loaded = await SessionRepository(db).get(account.id)
        assert loaded is not None
        # Raw api_hash is never stored in plaintext.
        assert "PLAIN-HASH" not in loaded.api_hash_encrypted
        assert open_secret(loaded.api_hash_encrypted, settings) == "PLAIN-HASH"
        assert loaded.has_session is True
        assert loaded.has_api_hash is True


async def test_repository_get_by_telegram_id() -> None:
    await init_models()
    async with session_scope() as db:
        repo = SessionRepository(db)
        account = UserSession(telegram_user_id=555, username="u", session_ref="r")
        await repo.add(account)
        await db.commit()
        found = await repo.get_by_telegram_id(555)
        assert found is not None
        assert found.username == "u"
        assert await repo.get_by_telegram_id(999) is None
        counts = await repo.count_by_status()
        assert counts.get(SessionStatus.DISCONNECTED.value) == 1
