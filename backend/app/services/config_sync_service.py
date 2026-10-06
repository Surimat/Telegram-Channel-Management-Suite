"""Config Sync service (v1.6).

Ties Owner Auth, the encrypted bundle and a :class:`ConfigSyncProvider` together:

* collect the local configuration into a versioned bundle (secrets excluded);
* encrypt it with the owner-derived key and hand the ciphertext to the provider;
* detect conflicts (local vs cloud revision) instead of a blind last-write-wins;
* restore a bundle on a new PC without silently overwriting local settings.

The live SQLite database is never synced; sessions and TDATA never enter a
bundle (D-106).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core import i18n
from backend.app.db.models.config_sync import (
    SYNC_STATE_AVAILABLE,
    SYNC_STATE_ERROR,
    SYNC_STATE_NEEDS_SETUP,
    SYNC_STATE_UNAVAILABLE,
    ConfigSyncState,
    SyncProviderKind,
)
from backend.app.db.repositories.owners import ConfigSyncRepository, OwnerRepository
from backend.app.providers.config_sync_base import ConfigSyncError, ConfigSyncProvider
from backend.app.services.config_bundle import (
    ConfigBundle,
    build_bundle,
    deserialize,
    scan_for_secrets,
    serialize,
)
from backend.app.services.events_service import EventsService

MODULE = "sync"

#: Setting keys that are safe and useful to carry between computers. Secrets are
#: excluded by :func:`config_bundle.sanitize_settings` regardless.
_UI_KEYS = ("show_explanations", "language")


class ConfigSyncError_(Exception):
    """A friendly, secret-free config-sync error."""

    def __init__(self, message: str, *, status_code: int = 400, how_to_fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.how_to_fix = how_to_fix


@dataclass(slots=True)
class SyncStatus:
    state: str
    state_label: str
    provider: str
    provider_label: str
    connected: bool
    enabled: bool
    owner_ready: bool
    local_revision: int
    cloud_revision: int
    device_id: str
    device_name: str
    cloud_device: str
    cloud_updated_at: str
    last_sync_at: str
    last_status: str
    message: str
    needs_reconnect: bool = False
    conflict: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "state_label": self.state_label,
            "provider": self.provider,
            "provider_label": self.provider_label,
            "connected": self.connected,
            "enabled": self.enabled,
            "owner_ready": self.owner_ready,
            "local_revision": self.local_revision,
            "cloud_revision": self.cloud_revision,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "cloud_device": self.cloud_device,
            "cloud_updated_at": self.cloud_updated_at,
            "last_sync_at": self.last_sync_at,
            "last_status": self.last_status,
            "message": self.message,
            "needs_reconnect": self.needs_reconnect,
            "conflict": self.conflict,
        }


@dataclass(slots=True)
class ConflictView:
    local_revision: int
    cloud_revision: int
    cloud_device: str
    cloud_updated_at: str
    local_device: str
    detected: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "local_revision": self.local_revision,
            "cloud_revision": self.cloud_revision,
            "cloud_device": self.cloud_device,
            "cloud_updated_at": self.cloud_updated_at,
            "local_device": self.local_device,
            "detected": self.detected,
        }


@dataclass(slots=True)
class RestorePreview:
    revision: int
    device_id: str
    device_name: str
    updated_at: str
    settings: dict[str, object] = field(default_factory=dict)
    ui: dict[str, object] = field(default_factory=dict)
    bot_count: int = 0
    channel_count: int = 0
    #: Local settings whose value differs from the bundle (shown before import).
    differing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "updated_at": self.updated_at,
            "settings": self.settings,
            "ui": self.ui,
            "bot_count": self.bot_count,
            "channel_count": self.channel_count,
            "differing": self.differing,
        }


class ConfigSyncService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        provider_factory=None,
        provider: ConfigSyncProvider | None = None,
    ) -> None:
        self.session = session
        self.state_repo = ConfigSyncRepository(session)
        self.owner_repo = OwnerRepository(session)
        self.events = EventsService(session)
        self._provider_factory = provider_factory
        self._provider = provider

    # --- provider plumbing ---------------------------------------------------
    def _resolve_provider(self, state: ConfigSyncState) -> ConfigSyncProvider | None:
        if self._provider is not None:
            return self._provider
        if self._provider_factory is None:
            from backend.app.providers.registry import build_config_sync_provider

            self._provider_factory = build_config_sync_provider
        if state.provider == SyncProviderKind.LOCAL:
            from backend.app.core import paths

            return self._provider_factory("local", directory=paths.data_dir() / "sync")
        if state.provider == SyncProviderKind.GOOGLE_DRIVE:
            transport = None
            if state.oauth_token_encrypted:
                from backend.app.core.security import open_secret
                from backend.app.providers.config_sync_gdrive import (
                    GoogleDriveHttpTransport,
                )

                try:
                    token = open_secret(state.oauth_token_encrypted)
                except ValueError:
                    token = ""
                if token:
                    transport = GoogleDriveHttpTransport(token)
            return self._provider_factory("google_drive", transport=transport)
        return None

    async def _state(self) -> ConfigSyncState:
        state = await self.state_repo.get_or_create()
        if not state.device_id:
            state.device_id = secrets.token_hex(8)
            state.device_name = state.device_name or "Этот компьютер"
            await self.session.flush()
        return state

    # --- key (from owner secret; never stored) -------------------------------
    async def _key(self, secret: str) -> bytes:
        from backend.app.core.owner_security import OwnerSecretError, derive_bundle_key

        owner = await self.owner_repo.get_single()
        if owner is None:
            raise ConfigSyncError_(
                i18n.translate("sync.need_owner"),
                status_code=409,
                how_to_fix="Создайте профиль владельца.",
            )
        try:
            return derive_bundle_key(secret, owner.sync_salt)
        except OwnerSecretError as exc:
            raise ConfigSyncError_(str(exc), status_code=400) from exc

    # --- status --------------------------------------------------------------
    async def status(self) -> SyncStatus:
        state = await self.state_repo.get_single()
        owner = await self.owner_repo.get_single()
        owner_ready = owner is not None
        if state is None:
            return SyncStatus(
                state=SYNC_STATE_UNAVAILABLE,
                state_label=i18n.translate(f"sync.state.{SYNC_STATE_UNAVAILABLE}"),
                provider="none",
                provider_label=i18n.translate("sync.provider.none"),
                connected=False,
                enabled=False,
                owner_ready=owner_ready,
                local_revision=0,
                cloud_revision=0,
                device_id="",
                device_name="",
                cloud_device="",
                cloud_updated_at="",
                last_sync_at="",
                last_status="",
                message=i18n.translate("sync.not_configured"),
            )

        provider = self._resolve_provider(state)
        connected = bool(provider and provider.available())
        needs_reconnect = (
            state.provider == SyncProviderKind.GOOGLE_DRIVE
            and bool(state.enabled)
            and not state.oauth_token_encrypted
        )
        if not owner_ready or not state.enabled or state.provider == SyncProviderKind.NONE:
            cap_state = SYNC_STATE_NEEDS_SETUP
        elif connected:
            cap_state = SYNC_STATE_AVAILABLE
        elif needs_reconnect:
            cap_state = SYNC_STATE_ERROR
        else:
            cap_state = SYNC_STATE_NEEDS_SETUP

        return SyncStatus(
            state=cap_state,
            state_label=i18n.translate(f"sync.state.{cap_state}"),
            provider=state.provider.value,
            provider_label=i18n.translate(f"sync.provider.{state.provider.value}"),
            connected=connected,
            enabled=state.enabled,
            owner_ready=owner_ready,
            local_revision=state.local_revision,
            cloud_revision=state.cloud_revision,
            device_id=state.device_id,
            device_name=state.device_name,
            cloud_device=state.cloud_device,
            cloud_updated_at=state.cloud_updated_at.isoformat() if state.cloud_updated_at else "",
            last_sync_at=state.last_sync_at.isoformat() if state.last_sync_at else "",
            last_status=state.last_status,
            message=state.last_message,
            needs_reconnect=needs_reconnect,
        )

    # --- configuration -------------------------------------------------------
    async def configure(self, provider: str, *, enabled: bool = True) -> SyncStatus:
        state = await self._state()
        try:
            kind = SyncProviderKind(str(provider))
        except ValueError as exc:
            raise ConfigSyncError_("Неизвестный провайдер синхронизации.") from exc
        state.provider = kind
        state.enabled = enabled
        await self.session.commit()
        await self.events.info(
            MODULE, f"Провайдер синхронизации: {kind.value}.", operation="configure"
        )
        return await self.status()

    async def connect_google(self, token: str, refresh: str = "") -> SyncStatus:
        """Store sealed OAuth tokens for Google Drive."""
        from backend.app.core.security import seal_secret

        state = await self._state()
        state.provider = SyncProviderKind.GOOGLE_DRIVE
        state.enabled = True
        state.oauth_token_encrypted = seal_secret(token) if token else ""
        state.oauth_refresh_encrypted = seal_secret(refresh) if refresh else ""
        await self.session.commit()
        await self.events.info(MODULE, "Google Drive подключён.", operation="connect")
        return await self.status()

    async def disconnect(self) -> SyncStatus:
        state = await self._state()
        state.oauth_token_encrypted = ""
        state.oauth_refresh_encrypted = ""
        state.enabled = False
        state.provider = SyncProviderKind.NONE
        await self.session.commit()
        await self.events.info(MODULE, "Провайдер синхронизации отключён.", operation="disconnect")
        return await self.status()

    # --- bundle build / restore ---------------------------------------------
    async def _collect_bundle(self, state: ConfigSyncState) -> ConfigBundle:
        from backend.app.services.settings_service import SettingsService

        settings_svc = SettingsService(self.session)
        raw: dict[str, object] = {}
        ui: dict[str, object] = {}
        for setting in await settings_svc.all():
            if setting.is_secret:
                continue
            if setting.key in _UI_KEYS:
                ui[setting.key] = setting.value
            else:
                raw[setting.key] = setting.value
        return build_bundle(
            settings=raw,
            ui=ui,
            revision=state.local_revision,
            device_id=state.device_id,
            device_name=state.device_name,
            owner_ref="owner",
        )

    async def _require_provider(self, state: ConfigSyncState) -> ConfigSyncProvider:
        provider = self._resolve_provider(state)
        if provider is None or not provider.available():
            raise ConfigSyncError_(
                i18n.translate("sync.provider_unavailable"),
                status_code=409,
                how_to_fix="Подключите Google Drive или выберите локальную папку.",
            )
        return provider

    async def upload(self, secret: str) -> SyncStatus:
        """Encrypt the current configuration and store it in the provider."""
        state = await self._state()
        provider = await self._require_provider(state)
        key = await self._key(secret)
        bundle = await self._collect_bundle(state)
        hits = scan_for_secrets(bundle)
        if hits:
            raise ConfigSyncError_(
                "В конфигурации найдены чувствительные поля.",
                status_code=500,
                how_to_fix="Сообщите об ошибке: поля " + ", ".join(hits) + ".",
            )
        payload = serialize(bundle, key)
        try:
            await provider.upload(payload, revision=bundle.config_revision)
        except ConfigSyncError as exc:
            await self._record_failure(state, exc.message)
            raise ConfigSyncError_(exc.message, status_code=502, how_to_fix=exc.how_to_fix) from exc
        state.cloud_revision = bundle.config_revision
        state.cloud_device = state.device_name
        state.cloud_updated_at = datetime.now(UTC)
        state.last_sync_at = datetime.now(UTC)
        state.last_status = "ok"
        state.last_message = i18n.translate("sync.uploaded")
        await self.session.commit()
        await self.events.info(MODULE, "Конфигурация выгружена.", operation="upload")
        return await self.status()

    async def download_preview(self, secret: str) -> RestorePreview:
        """Decrypt the cloud bundle and describe it without applying anything."""
        state = await self._state()
        provider = await self._require_provider(state)
        key = await self._key(secret)
        try:
            result = await provider.download()
        except ConfigSyncError as exc:
            raise ConfigSyncError_(exc.message, status_code=502, how_to_fix=exc.how_to_fix) from exc
        if result is None:
            raise ConfigSyncError_(
                i18n.translate("sync.no_bundle"),
                status_code=404,
                how_to_fix="Сначала выгрузите конфигурацию на другом компьютере.",
            )
        data, _meta = result
        try:
            bundle = deserialize(data, key)
        except Exception as exc:  # BundleError carries a friendly message
            message = getattr(exc, "message", i18n.translate("sync.wrong_password"))
            raise ConfigSyncError_(message, status_code=400) from exc

        local = await self._collect_bundle(state)
        differing = sorted(
            k
            for k, v in bundle.settings.items()
            if str(local.settings.get(k, "")) != str(v)
        )
        return RestorePreview(
            revision=bundle.config_revision,
            device_id=bundle.device_id,
            device_name=bundle.device_name,
            updated_at=bundle.updated_at,
            settings=dict(bundle.settings),
            ui=dict(bundle.ui),
            bot_count=len(bundle.bots),
            channel_count=len(bundle.channels),
            differing=differing,
        )

    async def download_apply(self, secret: str, *, keep_local: bool = False) -> SyncStatus:
        """Apply the cloud bundle locally (never silently overwrites on conflict)."""
        state = await self._state()
        provider = await self._require_provider(state)
        key = await self._key(secret)
        result = await provider.download()
        if result is None:
            raise ConfigSyncError_(i18n.translate("sync.no_bundle"), status_code=404)
        data, _meta = result
        try:
            bundle = deserialize(data, key)
        except Exception as exc:
            message = getattr(exc, "message", i18n.translate("sync.corrupt_bundle"))
            raise ConfigSyncError_(message, status_code=400) from exc

        conflict = (
            not keep_local
            and state.cloud_revision
            and bundle.config_revision != state.cloud_revision
            and bundle.device_id != state.device_id
        )
        if conflict:
            raise ConfigSyncError_(
                i18n.translate("sync.conflict"),
                status_code=409,
                how_to_fix="Выберите: оставить локальные или облачные настройки.",
            )

        from backend.app.services.settings_service import SettingsService

        settings_svc = SettingsService(self.session)
        for key_name, value in bundle.settings.items():
            await settings_svc.set(key_name, value)
        for key_name, value in bundle.ui.items():
            await settings_svc.set(key_name, value)

        state.cloud_revision = bundle.config_revision
        state.cloud_device = bundle.device_name
        state.cloud_updated_at = datetime.now(UTC)
        state.local_revision = max(state.local_revision, bundle.config_revision)
        state.last_sync_at = datetime.now(UTC)
        state.last_status = "ok"
        state.last_message = i18n.translate("sync.applied")
        await self.session.commit()
        await self.events.info(MODULE, "Конфигурация восстановлена.", operation="download")
        return await self.status()

    async def conflict(self) -> ConflictView:
        """Report whether the cloud bundle and the local revision disagree."""
        state = await self._state()
        provider = self._resolve_provider(state)
        local_device = state.device_name
        if provider is None or not provider.available():
            return ConflictView(
                local_revision=state.local_revision,
                cloud_revision=state.cloud_revision,
                cloud_device=state.cloud_device,
                cloud_updated_at="",
                local_device=local_device,
                detected=False,
            )
        try:
            result = await provider.download()
        except ConfigSyncError:
            result = None
        if result is None:
            return ConflictView(
                local_revision=state.local_revision,
                cloud_revision=state.cloud_revision,
                cloud_device=state.cloud_device,
                cloud_updated_at="",
                local_device=local_device,
                detected=False,
            )
        _data, meta = result
        detected = bool(
            state.cloud_revision
            and meta.revision
            and meta.revision != state.local_revision
            and meta.device_id not in ("", state.device_id)
        )
        return ConflictView(
            local_revision=state.local_revision,
            cloud_revision=meta.revision or state.cloud_revision,
            cloud_device=meta.device_name or state.cloud_device,
            cloud_updated_at=meta.updated_at,
            local_device=local_device,
            detected=detected,
        )

    async def _record_failure(self, state: ConfigSyncState, message: str) -> None:
        state.last_status = "error"
        state.last_message = message
        await self.session.commit()
        await self.events.warning(MODULE, "Синхронизация не удалась.", operation="sync")


def generate_state() -> str:
    """Opaque OAuth ``state`` value (CSRF protection for the loopback flow)."""
    return secrets.token_urlsafe(24)


__all__ = [
    "ConfigSyncError_",
    "ConfigSyncService",
    "ConflictView",
    "RestorePreview",
    "SyncStatus",
    "generate_state",
]
