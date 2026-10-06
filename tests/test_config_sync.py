"""Config Sync tests (v1.6): bundle codec, safety scan, local provider, service.

Uses a fake provider and a temporary directory — no network, no Google, no real
secret. Asserts that secrets never enter a bundle and that a wrong password
cannot decrypt it.
"""

from __future__ import annotations

import pytest

from backend.app.core.owner_security import derive_bundle_key
from backend.app.db.session import init_models, session_scope
from backend.app.providers.config_sync_base import RemoteBundle
from backend.app.services.config_bundle import (
    MAGIC,
    BundleError,
    build_bundle,
    deserialize,
    sanitize_settings,
    scan_for_secrets,
    serialize,
)
from backend.app.services.config_sync_service import ConfigSyncError_, ConfigSyncService
from backend.app.services.owner_auth_service import OwnerAuthService


def test_sanitize_drops_secret_looking_keys() -> None:
    cleaned = sanitize_settings(
        {
            "language": "ru",
            "show_explanations": "true",
            "telegram_api_hash": "deadbeef",
            "bot_token": "123:ABC",
            "session_path": "/tmp/x.session",
            "proxy_password": "p",
            "oauth_refresh": "r",
        }
    )
    assert cleaned == {"language": "ru", "show_explanations": "true"}


def test_bundle_roundtrip_and_tamper_detection() -> None:
    key = derive_bundle_key("pw", "salt")
    bundle = build_bundle(settings={"language": "ru"}, revision=3, device_id="dev1")
    payload = serialize(bundle, key)
    assert payload.startswith(MAGIC)
    restored = deserialize(payload, key)
    assert restored.settings["language"] == "ru"
    assert restored.config_revision == 3

    # A wrong key cannot decrypt.
    with pytest.raises(BundleError):
        deserialize(payload, derive_bundle_key("other", "salt"))

    # Flipping a byte breaks authentication.
    tampered = bytearray(payload)
    tampered[-1] ^= 0x01
    with pytest.raises(BundleError):
        deserialize(bytes(tampered), key)


def test_scan_reports_no_secrets_for_clean_bundle() -> None:
    bundle = build_bundle(settings={"language": "ru"}, ui={"show_explanations": "true"})
    assert scan_for_secrets(bundle) == []


def test_scan_detects_injected_secret() -> None:
    # build_bundle sanitizes, but extra content is walked too: prove the scan.
    bundle = build_bundle(extra={"nested": {"api_hash": "x"}})
    assert "api_hash" in scan_for_secrets(bundle)


class FakeProvider:
    """In-memory provider for the service tests (never touches disk/network)."""

    kind = "fake"

    def __init__(self) -> None:
        self.data: bytes | None = None
        self.revision = 0
        self.available_flag = True

    def available(self) -> bool:
        return self.available_flag

    async def upload(self, data: bytes, *, revision: int) -> RemoteBundle:
        self.data = data
        self.revision = revision
        return RemoteBundle(revision=revision, device_id="dev2", device_name="PC2", updated_at="")

    async def download(self):
        if self.data is None:
            return None
        return self.data, RemoteBundle(
            revision=self.revision, device_id="dev2", device_name="PC2", updated_at=""
        )

    async def delete(self) -> None:
        self.data = None


async def test_service_upload_and_restore_on_new_device() -> None:
    await init_models()
    provider = FakeProvider()
    async with session_scope() as session:
        owner = OwnerAuthService(session)
        await owner.create("owner pass")
        from backend.app.services.settings_service import SettingsService

        await SettingsService(session).set("language", "en")

        service = ConfigSyncService(session, provider=provider)
        await service.configure("local")
        status = await service.upload("owner pass")
        assert status.last_status == "ok"
        assert provider.data is not None
        # The stored bytes are ciphertext, not the settings in the clear.
        assert b"language" not in provider.data

        # A second install (fresh session state) restores the bundle.
        async with session_scope() as session2:
            service2 = ConfigSyncService(session2, provider=provider)
            # Same owner salt is required to decrypt: reuse the real one.
            preview = await service2.download_preview("owner pass")
            assert preview.ui.get("language") == "en"


async def test_service_wrong_password_rejected() -> None:
    await init_models()
    provider = FakeProvider()
    async with session_scope() as session:
        await OwnerAuthService(session).create("owner pass")
        service = ConfigSyncService(session, provider=provider)
        await service.configure("local")
        await service.upload("owner pass")
        with pytest.raises(ConfigSyncError_):
            await service.download_preview("wrong pass")


async def test_service_requires_provider() -> None:
    await init_models()
    async with session_scope() as session:
        await OwnerAuthService(session).create("owner pass")
        # No provider configured (defaults to NONE): upload must refuse.
        service = ConfigSyncService(session)
        with pytest.raises(ConfigSyncError_):
            await service.upload("owner pass")


async def test_local_provider_roundtrip(tmp_path) -> None:
    from backend.app.providers.config_sync_local import LocalConfigSyncProvider

    provider = LocalConfigSyncProvider(tmp_path / "sync")
    assert provider.available()
    await provider.upload(b"ciphertext", revision=1)
    result = await provider.download()
    assert result is not None
    data, _meta = result
    assert data == b"ciphertext"
    await provider.delete()
    assert await provider.download() is None
