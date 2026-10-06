"""Owner Auth tests (v1.6): crypto, service lifecycle, rate limiting.

No real secret is stored: the tests assert the verifier is one-way, the raw
secret never appears in the status, and repeated wrong attempts lock the login.
"""

from __future__ import annotations

import pytest

from backend.app.core.owner_security import (
    OwnerSecretError,
    derive_bundle_key,
    hash_secret,
    verify_secret,
)
from backend.app.db.session import init_models, session_scope
from backend.app.services.owner_auth_service import (
    MAX_FAILED_ATTEMPTS,
    OwnerAuthError,
    OwnerAuthService,
)


def test_hash_is_one_way_and_salted() -> None:
    verifier = hash_secret("hunter2")
    assert "hunter2" not in verifier
    assert verifier.startswith("pbkdf2_sha256$")
    # Same secret hashed twice differs (random salt) but both verify.
    assert verifier != hash_secret("hunter2")
    assert verify_secret("hunter2", verifier)
    assert not verify_secret("hunter3", verifier)
    assert not verify_secret("", verifier)


def test_derive_key_is_stable_and_salt_dependent() -> None:
    key_a = derive_bundle_key("pw", "salt-a")
    key_b = derive_bundle_key("pw", "salt-a")
    key_c = derive_bundle_key("pw", "salt-b")
    assert key_a == key_b
    assert key_a != key_c
    assert len(key_a) == 32
    with pytest.raises(OwnerSecretError):
        derive_bundle_key("", "salt")


async def test_create_login_change_and_no_secret_leak() -> None:
    await init_models()
    async with session_scope() as session:
        service = OwnerAuthService(session)
        assert not await service.exists()

        owner = await service.create("correct horse", display_name="Хозяин")
        assert owner.verifier.startswith("pbkdf2_sha256$")
        assert "correct horse" not in owner.verifier
        assert owner.sync_salt

        status = await service.status()
        assert status.exists and status.enabled
        # The status never carries the secret or the verifier.
        assert "correct horse" not in str(status.to_dict())
        assert "verifier" not in status.to_dict()

        await service.login("correct horse")
        with pytest.raises(OwnerAuthError):
            await service.login("wrong")

        await service.change_secret("correct horse", "new passphrase")
        await service.login("new passphrase")


async def test_duplicate_profile_rejected() -> None:
    await init_models()
    async with session_scope() as session:
        service = OwnerAuthService(session)
        await service.create("first pass")
        with pytest.raises(OwnerAuthError) as exc:
            await service.create("second pass")
        assert exc.value.status_code == 409


async def test_short_secret_rejected() -> None:
    await init_models()
    async with session_scope() as session:
        service = OwnerAuthService(session)
        with pytest.raises(OwnerAuthError):
            await service.create("ab")


async def test_lockout_after_repeated_failures() -> None:
    await init_models()
    async with session_scope() as session:
        service = OwnerAuthService(session)
        await service.create("right pass")
        for _ in range(MAX_FAILED_ATTEMPTS):
            with pytest.raises(OwnerAuthError):
                await service.login("bad")
        status = await service.status()
        assert status.locked
        # A correct password is refused while locked.
        with pytest.raises(OwnerAuthError) as exc:
            await service.login("right pass")
        assert exc.value.status_code == 423


async def test_derive_key_requires_correct_secret() -> None:
    await init_models()
    async with session_scope() as session:
        service = OwnerAuthService(session)
        await service.create("right pass")
        key = await service.derive_key("right pass")
        assert len(key) == 32
        with pytest.raises(OwnerAuthError):
            await service.derive_key("nope")
