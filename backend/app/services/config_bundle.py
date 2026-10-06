"""Versioned encrypted configuration bundle (v1.6).

The Suite never syncs its live SQLite database. Instead it builds a small,
**versioned** configuration document, serializes it to canonical JSON and
encrypts it with an authenticated cipher (AES-256-GCM) using the key derived from
the owner's secret. Only that ciphertext is stored by a provider (D-106).

What the bundle may contain: application settings, UI preferences, bot and
channel configuration, provider/scheduler/backup/notification configuration and
other safe persistent settings.

What it must **never** contain: ``.session`` files, TDATA, Telegram auth keys,
raw passwords, unencrypted bot tokens or arbitrary secrets. A denylist plus a
safety scan enforce this; the scan runs again before an export is written.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCHEMA_VERSION = 1
MAGIC = b"TCMS1"
_NONCE_BYTES = 12

#: Setting keys that must never leave the machine in a bundle. Compared
#: case-insensitively and by substring so variants are also excluded.
FORBIDDEN_KEY_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_hash",
    "api_id",
    "session",
    "tdata",
    "auth_key",
    "private_key",
    "oauth",
    "verifier",
    "recovery",
)


class BundleError(Exception):
    """A friendly, secret-free bundle error."""

    def __init__(self, message: str, *, how_to_fix: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix


@dataclass(slots=True)
class ConfigBundle:
    """The portable, non-secret configuration document."""

    schema_version: int = SCHEMA_VERSION
    config_revision: int = 0
    device_id: str = ""
    device_name: str = ""
    created_at: str = ""
    updated_at: str = ""
    owner_ref: str = ""
    settings: dict[str, object] = field(default_factory=dict)
    ui: dict[str, object] = field(default_factory=dict)
    bots: list[dict[str, object]] = field(default_factory=list)
    channels: list[dict[str, object]] = field(default_factory=list)
    providers: dict[str, object] = field(default_factory=dict)
    scheduler: dict[str, object] = field(default_factory=dict)
    backup: dict[str, object] = field(default_factory=dict)
    notifications: dict[str, object] = field(default_factory=dict)
    extra: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ConfigBundle:
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in FORBIDDEN_KEY_MARKERS)


def sanitize_settings(settings: dict[str, object]) -> dict[str, object]:
    """Drop any setting whose key looks secret; keep everything else."""
    return {k: v for k, v in settings.items() if not _is_forbidden_key(k)}


def build_bundle(
    *,
    settings: dict[str, object] | None = None,
    ui: dict[str, object] | None = None,
    bots: list[dict[str, object]] | None = None,
    channels: list[dict[str, object]] | None = None,
    providers: dict[str, object] | None = None,
    scheduler: dict[str, object] | None = None,
    backup: dict[str, object] | None = None,
    notifications: dict[str, object] | None = None,
    extra: dict[str, object] | None = None,
    revision: int = 0,
    device_id: str = "",
    device_name: str = "",
    owner_ref: str = "",
    created_at: str = "",
) -> ConfigBundle:
    """Assemble a bundle, excluding any secret-looking setting."""
    return ConfigBundle(
        schema_version=SCHEMA_VERSION,
        config_revision=revision,
        device_id=device_id,
        device_name=device_name,
        created_at=created_at or _now(),
        updated_at=_now(),
        owner_ref=owner_ref,
        settings=sanitize_settings(settings or {}),
        ui=dict(ui or {}),
        bots=list(bots or []),
        channels=list(channels or []),
        providers=dict(providers or {}),
        scheduler=dict(scheduler or {}),
        backup=dict(backup or {}),
        notifications=dict(notifications or {}),
        extra=dict(extra or {}),
    )


def _canonical_json(bundle: ConfigBundle) -> bytes:
    return json.dumps(
        bundle.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def serialize(bundle: ConfigBundle, key: bytes) -> bytes:
    """Encrypt a bundle with AES-256-GCM; returns ``MAGIC || nonce || ciphertext``.

    ``SCHEMA_VERSION`` is authenticated as associated data, so a downgrade or a
    version swap is detected as tampering.
    """
    if len(key) not in (16, 24, 32):
        raise BundleError("Некорректный ключ шифрования.")
    nonce = os.urandom(_NONCE_BYTES)
    aad = MAGIC + str(bundle.schema_version).encode("ascii")
    ciphertext = AESGCM(key).encrypt(nonce, _canonical_json(bundle), aad)
    return MAGIC + nonce + ciphertext


def deserialize(data: bytes, key: bytes) -> ConfigBundle:
    """Decrypt and integrity-check a bundle. Raises :class:`BundleError`."""
    if not data.startswith(MAGIC):
        raise BundleError(
            "Файл конфигурации не распознан.",
            how_to_fix="Выберите файл, созданный этой программой.",
        )
    nonce = data[len(MAGIC) : len(MAGIC) + _NONCE_BYTES]
    ciphertext = data[len(MAGIC) + _NONCE_BYTES :]
    if len(nonce) != _NONCE_BYTES or not ciphertext:
        raise BundleError("Файл конфигурации повреждён.")
    # Try the current schema version; a version mismatch is reported as corrupt.
    aad = MAGIC + str(SCHEMA_VERSION).encode("ascii")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise BundleError(
            "Не удалось расшифровать конфигурацию: неверный пароль или файл повреждён.",
            how_to_fix="Проверьте пароль владельца.",
        ) from exc
    try:
        parsed = json.loads(plaintext.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BundleError("Файл конфигурации повреждён.") from exc
    if not isinstance(parsed, dict):
        raise BundleError("Файл конфигурации повреждён.")
    bundle = ConfigBundle.from_dict(parsed)
    if bundle.schema_version != SCHEMA_VERSION:
        raise BundleError(
            "Версия файла конфигурации не поддерживается.",
            how_to_fix="Обновите приложение или выберите другой файл.",
        )
    return bundle


def scan_for_secrets(bundle: ConfigBundle) -> list[str]:
    """Return forbidden key names present in the bundle (should always be empty)."""
    hits: list[str] = []

    def _walk(value: object) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if _is_forbidden_key(str(k)):
                    hits.append(str(k))
                _walk(v)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(bundle.to_dict())
    return sorted(set(hits))


__all__ = [
    "FORBIDDEN_KEY_MARKERS",
    "MAGIC",
    "SCHEMA_VERSION",
    "BundleError",
    "ConfigBundle",
    "build_bundle",
    "deserialize",
    "sanitize_settings",
    "scan_for_secrets",
    "serialize",
]
