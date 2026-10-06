"""Capability graph (v1.5 consistency layer).

A single, machine-readable description of what the product can do and what each
capability **requires**. The UI, the Promotion Wizard and the Consistency Auditor
all read this instead of re-encoding "does this need a session?" rules in every
view (D-094).

Requirements are atomic flags:

* ``channel``             — a channel is registered;
* ``bot_binding``         — a bot is bound to the channel (and healthy);
* ``user_session``        — a connected user account exists;
* ``permission``          — the account's rights on the channel were verified;
* ``posting_capability``  — a bot with posting rights is bound;
* ``encoder_model``       — the lightweight Mini-AI model is installed;
* ``ffmpeg``              — the media tooling is present.

A capability is ``available`` when every requirement is met, ``unavailable``
when none is met, and ``needs_setup`` otherwise. A capability may declare a
``minimal`` subset that yields ``partial`` (usable in a limited way) — e.g.
direct invites can be prepared before the account's rights are verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core import i18n

# --- Atomic requirements ----------------------------------------------------
REQ_CHANNEL = "channel"
REQ_BOT_BINDING = "bot_binding"
REQ_USER_SESSION = "user_session"
REQ_PERMISSION = "permission"
REQ_POSTING_CAPABILITY = "posting_capability"
REQ_ENCODER_MODEL = "encoder_model"
REQ_FFMPEG = "ffmpeg"
REQ_OWNER_AUTH = "owner_auth"
REQ_GOOGLE_DRIVE = "google_drive"

ALL_REQUIREMENTS = (
    REQ_CHANNEL,
    REQ_BOT_BINDING,
    REQ_USER_SESSION,
    REQ_PERMISSION,
    REQ_POSTING_CAPABILITY,
    REQ_ENCODER_MODEL,
    REQ_FFMPEG,
    REQ_OWNER_AUTH,
    REQ_GOOGLE_DRIVE,
)

# --- Capability states ------------------------------------------------------
STATE_AVAILABLE = "available"
STATE_PARTIAL = "partial"
STATE_NEEDS_SETUP = "needs_setup"
STATE_UNAVAILABLE = "unavailable"
#: The capability is described in the registry but has no implementation yet.
#: It is deliberately distinct from ``unavailable`` (which means "not set up"):
#: the user cannot fix this by configuring anything.
STATE_NOT_IMPLEMENTED = "not_implemented"

STATE_ORDER = {
    STATE_AVAILABLE: 0,
    STATE_PARTIAL: 1,
    STATE_NEEDS_SETUP: 2,
    STATE_UNAVAILABLE: 3,
    STATE_NOT_IMPLEMENTED: 4,
}


@dataclass(frozen=True)
class Capability:
    """A product capability and the requirements it depends on.

    ``implemented`` guards against a *false* ``available``: a capability that is
    listed in the registry (so the UI can explain it) but has no real
    implementation behind it must never evaluate to ``available``. A missing
    implementation is an absolute prerequisite, not a user setup step, so it
    forces ``unavailable`` regardless of the requirement context.
    """

    key: str
    title_ru: str
    title_en: str
    requires: tuple[str, ...] = ()
    minimal: tuple[str, ...] = ()
    note_ru: str = ""
    note_en: str = ""
    implemented: bool = True

    def title(self, language: str | None = None) -> str:
        return self.title_en if i18n.normalize_language(language) == "en" else self.title_ru

    def note(self, language: str | None = None) -> str:
        return self.note_en if i18n.normalize_language(language) == "en" else self.note_ru


# The registry. Keys are stable identifiers used by the UI and the wizard.
CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        key="reaction",
        title_ru="Автоматические реакции",
        title_en="Automatic reactions",
        requires=(REQ_CHANNEL, REQ_BOT_BINDING),
    ),
    Capability(
        key="bot_only_analytics",
        title_ru="Аналитика без аккаунта",
        title_en="Analytics without an account",
        requires=(REQ_CHANNEL, REQ_BOT_BINDING),
        note_ru="Историческая информация недоступна этому типу подключения.",
        note_en="Historical information is unavailable for this connection type.",
    ),
    Capability(
        key="audience_scan",
        title_ru="Сбор аудитории",
        title_en="Audience scanning",
        requires=(REQ_CHANNEL, REQ_USER_SESSION),
    ),
    Capability(
        key="direct_invite",
        title_ru="Приглашения напрямую",
        title_en="Direct invites",
        requires=(REQ_CHANNEL, REQ_USER_SESSION, REQ_PERMISSION),
        minimal=(REQ_CHANNEL, REQ_USER_SESSION),
    ),
    Capability(
        key="content_publish",
        title_ru="Публикация контента",
        title_en="Content publishing",
        requires=(REQ_CHANNEL, REQ_POSTING_CAPABILITY),
    ),
    Capability(
        key="media_conversion",
        title_ru="Обработка медиа",
        title_en="Media processing",
        requires=(REQ_FFMPEG,),
        implemented=False,
        note_ru="Обработка медиа (сжатие, конвертация, миниатюры) в этой версии не реализована.",
        note_en=(
            "Media processing (compression, conversion, thumbnails) is not "
            "implemented in this version."
        ),
    ),
    Capability(
        key="ai_ru",
        title_ru="Мини-ИИ (русский)",
        title_en="Mini-AI (Russian)",
        requires=(REQ_ENCODER_MODEL,),
    ),
    Capability(
        key="donor_discovery",
        title_ru="Поиск источников",
        title_en="Donor discovery",
        requires=(),
        note_ru="Ручной ввод доступен всегда.",
        note_en="Manual entry is always available.",
    ),
    Capability(
        key="config_sync",
        title_ru="Синхронизация конфигурации",
        title_en="Configuration sync",
        requires=(REQ_OWNER_AUTH, REQ_GOOGLE_DRIVE),
        minimal=(REQ_OWNER_AUTH,),
        note_ru=(
            "Переносит настройки на новый компьютер через зашифрованный файл. "
            "Файлы сессий и база данных не синхронизируются."
        ),
        note_en=(
            "Moves settings to a new computer via an encrypted bundle. Session "
            "files and the database are never synced."
        ),
    ),
)

CAPABILITIES_BY_KEY = {c.key: c for c in CAPABILITIES}


@dataclass(slots=True)
class CapabilityState:
    """The evaluated state of one capability for a concrete install."""

    key: str
    title: str
    state: str
    state_label: str
    requires: list[str] = field(default_factory=list)
    satisfied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    missing_fixes: list[str] = field(default_factory=list)
    note: str = ""
    implemented: bool = True

    @property
    def available(self) -> bool:
        return self.state == STATE_AVAILABLE

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "state": self.state,
            "state_label": self.state_label,
            "requires": self.requires,
            "satisfied": self.satisfied,
            "missing": self.missing,
            "missing_fixes": self.missing_fixes,
            "note": self.note,
            "implemented": self.implemented,
        }


def requirement_label(req: str, language: str | None = None) -> str:
    return i18n.translate(f"cap.{req}", language, default=req)


def requirement_fix(req: str, language: str | None = None) -> str:
    return i18n.translate(f"cap.{req}.fix", language, default="")


def state_label(state: str, language: str | None = None) -> str:
    return i18n.translate(f"cap.state.{state}", language, default=state)


def evaluate(
    capability: Capability, context: dict[str, bool], language: str | None = None
) -> CapabilityState:
    """Evaluate one capability against a requirement context.

    A capability with no implementation is always ``not_implemented``: the
    registry entry exists so the UI can explain *why* the feature is absent, but
    it must never report ``available``/``partial`` just because the registry
    lists it (the exact failure this guard exists to prevent).
    """
    if not capability.implemented:
        return CapabilityState(
            key=capability.key,
            title=capability.title(language),
            state=STATE_NOT_IMPLEMENTED,
            state_label=state_label(STATE_NOT_IMPLEMENTED, language),
            requires=[requirement_label(r, language) for r in capability.requires],
            satisfied=[],
            missing=[],
            missing_fixes=[],
            note=capability.note(language),
            implemented=False,
        )

    satisfied = [r for r in capability.requires if context.get(r)]
    missing = [r for r in capability.requires if not context.get(r)]

    # A requirement that names another capability is only satisfied when that
    # capability is actually implemented; otherwise the dependent capability must
    # not report available/partial (D-099).
    unimplemented = {c.key for c in CAPABILITIES if not c.implemented}
    missing.extend(r for r in satisfied if r in unimplemented)
    satisfied = [r for r in satisfied if r not in unimplemented]

    if not capability.requires or not missing:
        state = STATE_AVAILABLE
    elif capability.minimal and all(
        context.get(r) and r not in unimplemented for r in capability.minimal
    ):
        state = STATE_PARTIAL
    elif satisfied:
        state = STATE_NEEDS_SETUP
    else:
        state = STATE_UNAVAILABLE

    return CapabilityState(
        key=capability.key,
        title=capability.title(language),
        state=state,
        state_label=state_label(state, language),
        requires=[requirement_label(r, language) for r in capability.requires],
        satisfied=[requirement_label(r, language) for r in satisfied],
        missing=[requirement_label(r, language) for r in missing],
        missing_fixes=[requirement_fix(r, language) for r in missing],
        note=capability.note(language),
        implemented=True,
    )


def evaluate_all(context: dict[str, bool], language: str | None = None) -> list[CapabilityState]:
    """Evaluate every registered capability for a requirement context."""
    return [evaluate(c, context, language) for c in CAPABILITIES]


def state_for(key: str, context: dict[str, bool], language: str | None = None) -> CapabilityState:
    capability = CAPABILITIES_BY_KEY[key]
    return evaluate(capability, context, language)


async def context_from_db(
    session: AsyncSession,
    *,
    encoder_installed: bool | None = None,
) -> dict[str, bool]:
    """Build a requirement context from the live database.

    Best-effort: a failing subsystem yields ``False`` for its requirement rather
    than raising, so the capability view always renders.
    """
    context = dict.fromkeys(ALL_REQUIREMENTS, False)

    from backend.app.db.models.binding import FUNCTION_POSTING, BindingStatus
    from backend.app.db.models.session import SessionStatus
    from backend.app.db.repositories.bindings import BindingRepository
    from backend.app.db.repositories.channels import ChannelRepository
    from backend.app.db.repositories.permissions import PermissionCheckRepository
    from backend.app.db.repositories.sessions import SessionRepository

    try:
        channels, count = await ChannelRepository(session).list()
        context[REQ_CHANNEL] = count > 0 or bool(channels)
    except Exception:  # pragma: no cover - defensive
        pass

    try:
        all_bindings = await BindingRepository(session).list_all()
        context[REQ_BOT_BINDING] = any(
            b.status == BindingStatus.READY for b in all_bindings
        )
        context[REQ_POSTING_CAPABILITY] = any(
            b.status == BindingStatus.READY and b.function == FUNCTION_POSTING
            for b in all_bindings
        )
    except Exception:  # pragma: no cover - defensive
        pass

    try:
        sessions, _ = await SessionRepository(session).list()
        context[REQ_USER_SESSION] = any(
            s.status == SessionStatus.CONNECTED for s in sessions
        )
    except Exception:  # pragma: no cover - defensive
        pass

    try:
        latest = await PermissionCheckRepository(session).latest()
        context[REQ_PERMISSION] = bool(latest and latest.can_invite)
    except Exception:  # pragma: no cover - defensive
        pass

    if encoder_installed is not None:
        context[REQ_ENCODER_MODEL] = bool(encoder_installed)
    else:
        try:
            from backend.app.services.encoder_service import EncoderService

            status = await EncoderService(session).status()
            context[REQ_ENCODER_MODEL] = bool(getattr(status, "installed", False))
        except Exception:  # pragma: no cover - defensive
            pass

    try:
        from backend.app.services.owner_auth_service import OwnerAuthService

        context[REQ_OWNER_AUTH] = await OwnerAuthService(session).exists()
    except Exception:  # pragma: no cover - defensive
        pass

    try:
        from backend.app.services.config_sync_service import ConfigSyncService

        sync_status = await ConfigSyncService(session).status()
        context[REQ_GOOGLE_DRIVE] = bool(sync_status.connected)
    except Exception:  # pragma: no cover - defensive
        pass

    return context


__all__ = [
    "ALL_REQUIREMENTS",
    "CAPABILITIES",
    "CAPABILITIES_BY_KEY",
    "REQ_BOT_BINDING",
    "REQ_CHANNEL",
    "REQ_ENCODER_MODEL",
    "REQ_FFMPEG",
    "REQ_GOOGLE_DRIVE",
    "REQ_OWNER_AUTH",
    "REQ_PERMISSION",
    "REQ_POSTING_CAPABILITY",
    "REQ_USER_SESSION",
    "STATE_AVAILABLE",
    "STATE_NEEDS_SETUP",
    "STATE_NOT_IMPLEMENTED",
    "STATE_PARTIAL",
    "STATE_UNAVAILABLE",
    "Capability",
    "CapabilityState",
    "context_from_db",
    "evaluate",
    "evaluate_all",
    "requirement_fix",
    "requirement_label",
    "state_for",
    "state_label",
]
