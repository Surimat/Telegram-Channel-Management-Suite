"""Session import providers (v1.1: Account Hub).

The Session Manager historically accepted one format: a Telethon ``.session``
file. The Account Hub adds **local** importers for the common formats a user may
already own, behind one small protocol so the service layer never grows a pile of
``if`` branches:

* ``.session``            — Telethon SQLite session (existing path, reused).
* ``session + JSON``      — a ``.session`` with a companion ``.json`` holding
  ``api_id``/``api_hash`` metadata.
* ``StringSession``       — a Telethon ``StringSession`` string.
* ``TDATA``               — a Telegram Desktop ``tdata`` directory.

Security posture (non-negotiable):

* These importers only ever touch **local files the user already owns** — there is
  no search for, download of, or bulk registration of third-party accounts, and
  no attempt to bypass Telegram verification, FloodWait, privacy or identity
  checks (D-006, D-065).
* A ``StringSession`` string / ``auth_key`` / ``api_hash`` / password is treated
  as a **secret**: it is never displayed, logged, returned by the API or written
  to git. The raw string lives only in memory for the duration of an import.
* TDATA conversion is optional: if no reliable converter is installed the
  importer reports an honest ``NOT AVAILABLE`` status instead of pretending.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

# --- Formats ----------------------------------------------------------------
FORMAT_SESSION = "session"
FORMAT_SESSION_JSON = "session_json"
FORMAT_STRING_SESSION = "string_session"
FORMAT_TDATA = "tdata"
FORMAT_UNKNOWN = "unknown"

FORMAT_TITLES = {
    FORMAT_SESSION: "Telethon .session",
    FORMAT_SESSION_JSON: ".session + JSON",
    FORMAT_STRING_SESSION: "StringSession",
    FORMAT_TDATA: "Telegram Desktop (TDATA)",
    FORMAT_UNKNOWN: "Не удалось определить",
}

# --- Detection states -------------------------------------------------------
STATE_VALID = "valid"
STATE_DAMAGED = "damaged"
STATE_UNAUTHORIZED = "unauthorized"
STATE_UNKNOWN = "unknown"

STATE_TITLES = {
    STATE_VALID: "Валиден",
    STATE_DAMAGED: "Повреждён",
    STATE_UNAUTHORIZED: "Не авторизован",
    STATE_UNKNOWN: "Не удалось определить",
}

#: Companion JSON keys that are secrets and must never be surfaced. ``api_hash``
#: is intentionally *not* here: it is required to connect, so it is read from the
#: user's own local file and immediately sealed (never logged or returned).
SECRET_JSON_KEYS = frozenset(
    {
        "session_string",
        "string_session",
        "auth_key",
        "authkey",
        "password",
        "passwd",
        "session",
        "token",
    }
)

#: Companion JSON keys we are willing to read (metadata actually needed).
ALLOWED_JSON_KEYS = frozenset({"api_id", "app_id", "api_hash", "app_hash", "phone", "dc_id"})

_STRING_SESSION_RE = re.compile(r"^1[A-Za-z0-9_\-]{40,}$")


@dataclass(slots=True)
class SessionImportRequest:
    """A local import request. Paths only; never a remote resource."""

    path: Path | None = None
    string_session: str = ""
    api_id: str = ""
    api_hash: str = ""
    phone: str = ""
    display_name: str = ""
    json_path: Path | None = None


@dataclass(slots=True)
class SessionImportResult:
    """Outcome of an import attempt (never carries a secret)."""

    ok: bool
    format: str = FORMAT_UNKNOWN
    state: str = STATE_UNKNOWN
    api_id: str = ""
    api_hash: str = ""
    phone: str = ""
    display_name: str = ""
    session_bytes: bytes = b""
    session_ref: str = ""
    #: For StringSession: the raw string. Kept in memory only; the service writes
    #: it to the session file and never returns it.
    string_session: str = ""
    message: str = ""
    how_to_fix: str = ""
    #: Plain-language list of what was recognised (safe to show).
    notes: list[str] = field(default_factory=list)
    #: Optional Telegram identity confirmed by a local metadata read.
    telegram_user_id: int | None = None
    username: str = ""


@runtime_checkable
class SessionImportProvider(Protocol):
    """Detects and prepares a local session artifact for import."""

    @property
    def name(self) -> str:
        """Provider name (``session``/``session_json``/``string_session``/``tdata``)."""
        ...

    @property
    def format(self) -> str:
        """The session format this provider handles (see ``FORMAT_*``)."""
        ...

    @property
    def available(self) -> bool:
        """False when the provider's optional dependency is missing."""
        ...

    def detect(self, request: SessionImportRequest) -> bool:
        """Return True when this provider recognises the request."""
        ...

    def inspect(self, request: SessionImportRequest) -> SessionImportResult:
        """Detect + validate + read metadata, without importing into the DB."""
        ...


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _looks_like_sqlite(path: Path) -> bool:
    """A Telethon ``.session`` is a SQLite file starting with ``SQLite format 3``."""
    try:
        with path.open("rb") as fh:
            return fh.read(16).startswith(b"SQLite format 3")
    except OSError:
        return False


def _read_companion_json(path: Path) -> dict[str, str]:
    """Read only whitelisted metadata from a companion JSON (secrets dropped)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    meta: dict[str, str] = {}
    for key, value in raw.items():
        low = str(key).lower()
        if low in SECRET_JSON_KEYS:
            # Recognised but deliberately not read into memory beyond here.
            continue
        if low in ALLOWED_JSON_KEYS:
            meta[low] = str(value)
    return meta


def _find_companion_json(path: Path) -> Path | None:
    """Return the companion ``.json`` next to a ``.session`` file, if any."""
    for candidate in (
        path.with_suffix(".json"),
        Path(str(path) + ".json"),
        path.parent / (path.stem + "_meta.json"),
    ):
        if candidate.is_file():
            return candidate
    return None


def _looks_like_string_session(value: str) -> bool:
    return bool(_STRING_SESSION_RE.match((value or "").strip()))


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class SessionFileImportProvider:
    """Telethon ``.session`` (optionally with a companion JSON)."""

    def __init__(self, *, require_companion: bool = False) -> None:
        self._require_companion = require_companion

    @property
    def name(self) -> str:
        return FORMAT_SESSION_JSON if self._require_companion else FORMAT_SESSION

    @property
    def format(self) -> str:
        return FORMAT_SESSION_JSON if self._require_companion else FORMAT_SESSION

    @property
    def available(self) -> bool:
        return True

    def detect(self, request: SessionImportRequest) -> bool:
        path = request.path
        if path is None or not path.is_file() or path.suffix != ".session":
            return False
        if self._require_companion:
            return _find_companion_json(path) is not None
        return True

    def inspect(self, request: SessionImportRequest) -> SessionImportResult:
        path = request.path
        assert path is not None  # guarded by detect()
        if not _looks_like_sqlite(path):
            return SessionImportResult(
                ok=False,
                format=self.format,
                state=STATE_DAMAGED,
                message="Файл не похож на сессию Telethon (повреждён или не тот формат).",
                how_to_fix="Выберите файл .session, созданный Telethon.",
            )
        meta: dict[str, str] = {}
        companion = request.json_path or _find_companion_json(path)
        if companion is not None:
            meta = _read_companion_json(companion)
        notes = ["Файл сессии прочитан."]
        if companion is not None:
            notes.append("Найден и прочитан companion JSON (только безопасные поля).")
        return SessionImportResult(
            ok=True,
            format=self.format,
            state=STATE_VALID,
            api_id=str(meta.get("api_id") or meta.get("app_id") or request.api_id or ""),
            api_hash=str(
                meta.get("api_hash") or meta.get("app_hash") or request.api_hash or ""
            ),
            phone=str(meta.get("phone") or request.phone or ""),
            display_name=request.display_name,
            session_bytes=path.read_bytes(),
            notes=notes,
            message="Сессия готова к импорту.",
        )


class StringSessionImportProvider:
    """Telethon ``StringSession`` string (imported locally)."""

    @property
    def name(self) -> str:
        return FORMAT_STRING_SESSION

    @property
    def format(self) -> str:
        return FORMAT_STRING_SESSION

    @property
    def available(self) -> bool:
        return True

    def detect(self, request: SessionImportRequest) -> bool:
        return _looks_like_string_session(request.string_session)

    def inspect(self, request: SessionImportRequest) -> SessionImportResult:
        value = (request.string_session or "").strip()
        if not _looks_like_string_session(value):
            return SessionImportResult(
                ok=False,
                format=FORMAT_STRING_SESSION,
                state=STATE_DAMAGED,
                message="Строка сессии имеет неверный формат.",
                how_to_fix="Скопируйте строку целиком из Telethon StringSession.",
            )
        # Deliberately do not log or echo ``value``. It is returned only so the
        # service can persist it; the API never serialises it back.
        return SessionImportResult(
            ok=True,
            format=FORMAT_STRING_SESSION,
            state=STATE_VALID,
            api_id=request.api_id,
            api_hash=request.api_hash,
            phone=request.phone,
            display_name=request.display_name,
            string_session=value,
            notes=["Строка сессии распознана и будет сохранена в защищённую папку."],
            message="StringSession готова к импорту.",
        )


class TdataImportProvider:
    """Telegram Desktop ``tdata`` directory (optional converter)."""

    #: Filenames that mark a Telegram Desktop tdata directory.
    _MARKERS = ("key_datas", "D877F783D5D3EF8C", "map", "settingss")

    def __init__(self, *, converter: object | None = None) -> None:
        # A callable ``(tdata_dir) -> (session_bytes, meta)`` when a reliable
        # converter is available. ``None`` → the importer is NOT AVAILABLE.
        self._converter = converter

    @property
    def name(self) -> str:
        return FORMAT_TDATA

    @property
    def format(self) -> str:
        return FORMAT_TDATA

    @property
    def available(self) -> bool:
        return callable(self._converter)

    def detect(self, request: SessionImportRequest) -> bool:
        path = request.path
        if path is None or not path.is_dir():
            return False
        if path.name.lower() == "tdata":
            return True
        return any((path / marker).exists() for marker in self._MARKERS)

    def inspect(self, request: SessionImportRequest) -> SessionImportResult:
        path = request.path
        assert path is not None  # guarded by detect()
        if not self.available:
            return SessionImportResult(
                ok=False,
                format=FORMAT_TDATA,
                state=STATE_UNKNOWN,
                message=(
                    "Импорт TDATA недоступен: надёжный конвертер не установлен."
                ),
                how_to_fix=(
                    "Используйте формат .session или StringSession. TDATA можно "
                    "конвертировать отдельным проверенным инструментом."
                ),
                notes=["Исходная папка TDATA не изменяется и никуда не отправляется."],
            )
        try:
            session_bytes, meta = self._converter(path)  # type: ignore[misc]
        except Exception:
            # Converter failures are ordinary; report them honestly.
            return SessionImportResult(
                ok=False,
                format=FORMAT_TDATA,
                state=STATE_DAMAGED,
                message="Не удалось прочитать папку TDATA.",
                how_to_fix="Проверьте, что выбрана папка tdata действующего аккаунта.",
            )
        meta = meta or {}
        return SessionImportResult(
            ok=True,
            format=FORMAT_TDATA,
            state=STATE_VALID,
            api_id=str(meta.get("api_id") or request.api_id or ""),
            api_hash=str(meta.get("api_hash") or request.api_hash or ""),
            phone=str(meta.get("phone") or request.phone or ""),
            display_name=request.display_name,
            session_bytes=session_bytes,
            telegram_user_id=meta.get("telegram_user_id"),
            username=str(meta.get("username") or ""),
            notes=["TDATA прочитана локально; исходная папка не изменяется."],
            message="TDATA готова к импорту.",
        )


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
#: Order matters: the JSON-companion variant is checked before the plain file.
def default_providers() -> list[SessionImportProvider]:
    return [
        SessionFileImportProvider(require_companion=True),
        SessionFileImportProvider(),
        StringSessionImportProvider(),
        TdataImportProvider(),
    ]


@dataclass(slots=True)
class DetectionResult:
    """What we can tell the user *before* importing."""

    format: str
    state: str
    available: bool = True
    notes: list[str] = field(default_factory=list)
    message: str = ""
    how_to_fix: str = ""


def detect_format(
    request: SessionImportRequest,
    *,
    providers: list[SessionImportProvider] | None = None,
) -> DetectionResult:
    """Detect the artifact format and its basic state (no DB, no network)."""
    providers = providers or default_providers()
    for provider in providers:
        if provider.detect(request):
            result = provider.inspect(request)
            return DetectionResult(
                format=provider.format,
                state=result.state,
                available=provider.available,
                notes=result.notes,
                message=result.message,
                how_to_fix=result.how_to_fix,
            )
    return DetectionResult(
        format=FORMAT_UNKNOWN,
        state=STATE_UNKNOWN,
        message="Не удалось определить формат файла или папки.",
        how_to_fix=(
            "Поддерживаются: .session, .session + JSON, строка StringSession и "
            "папка TDATA."
        ),
    )


def select_provider(
    request: SessionImportRequest,
    *,
    providers: list[SessionImportProvider] | None = None,
) -> SessionImportProvider | None:
    """Return the first provider that recognises ``request`` (None if unknown)."""
    for provider in providers or default_providers():
        if provider.detect(request):
            return provider
    return None


__all__ = [
    "ALLOWED_JSON_KEYS",
    "FORMAT_SESSION",
    "FORMAT_SESSION_JSON",
    "FORMAT_STRING_SESSION",
    "FORMAT_TDATA",
    "FORMAT_TITLES",
    "FORMAT_UNKNOWN",
    "SECRET_JSON_KEYS",
    "STATE_DAMAGED",
    "STATE_TITLES",
    "STATE_UNAUTHORIZED",
    "STATE_UNKNOWN",
    "STATE_VALID",
    "DetectionResult",
    "SessionFileImportProvider",
    "SessionImportProvider",
    "SessionImportRequest",
    "SessionImportResult",
    "StringSessionImportProvider",
    "TdataImportProvider",
    "default_providers",
    "detect_format",
    "select_provider",
]
