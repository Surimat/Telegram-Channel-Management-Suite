"""Consistency Auditor (v1.5 integration guard).

Detects architectural drift between modules, not just runtime errors: a DB model
without a migration, a scheduler job without a handler, a documented endpoint
that no longer exists, a help topic the UI references but the catalog lacks, a
setting no module reads, a reaction profile whose emoji the channel does not
support (D-092).

Findings carry a severity (``error`` / ``warning`` / ``info``) and a confidence
(``high`` / ``medium`` / ``low``). The auditor is deliberately conservative: it
prefers ``warning``/``info`` over ``error`` when a check is heuristic, so it
never cries wolf (D-093).

It runs two ways:

* **runtime** — ``GET /api/v1/consistency`` feeds the "Проверка целостности"
  panel in Diagnostics;
* **CI** — ``tests/test_architecture_consistency.py`` calls
  :func:`run_static_checks`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.services.consistency_checks import run_static_checks
from backend.app.services.consistency_types import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    ConsistencyReport,
    Finding,
    build_report,
)

__all__ = [
    "ConsistencyAuditor",
    "ConsistencyReport",
    "Finding",
    "build_report",
    "run_static_checks",
]


class ConsistencyAuditor:
    """Run runtime + static consistency checks against the live install."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def run(self) -> ConsistencyReport:
        findings: list[Finding] = []
        findings.extend(await self._runtime_findings())
        findings.extend(run_static_checks())
        return build_report(findings)

    # ------------------------------------------------------------------
    # Runtime (DB-backed) checks
    # ------------------------------------------------------------------
    async def _runtime_findings(self) -> list[Finding]:
        findings: list[Finding] = []
        for check in (
            self._check_channel_aware,
            self._check_audience_session,
            self._check_reaction_capability,
            self._check_dead_settings,
        ):
            try:
                findings.extend(await check())
            except Exception as exc:  # a failing check is itself a finding
                findings.append(
                    Finding(
                        id=f"audit.check_failed.{check.__name__}",
                        category="integration",
                        severity=SEVERITY_ERROR,
                        confidence="high",
                        title="Проверка целостности не выполнилась",
                        detail=f"{check.__name__}: {type(exc).__name__}: {exc}",
                        why=(
                            "Проверка не отработала, поэтому её результат неизвестен — "
                            "это не «всё в порядке»."
                        ),
                        how_to_fix="Исправьте ошибку в самой проверке (см. detail) и повторите.",
                        subsystem="audit",
                    )
                )
        return findings

    async def _check_channel_aware(self) -> list[Finding]:
        """Warn when a channel-aware module has rows with no channel reference."""
        from sqlalchemy import func, select

        from backend.app.db.models.content import ContentSource

        findings: list[Finding] = []
        # `ContentSource.channel_id` is the registry link (D-051). This used to
        # target `ContentItem`, which has no such column — the resulting error was
        # swallowed and the check silently reported nothing (found by the
        # meta-audit, D-100).
        stmt = (
            select(func.count())
            .select_from(ContentSource)
            .where(ContentSource.channel_id == "")
        )
        count = int((await self.session.execute(stmt)).scalar_one())
        if count:
            findings.append(
                Finding(
                    id="channel-aware.content_source",
                    category="channels",
                    severity=SEVERITY_WARNING,
                    confidence="medium",
                    title="ContentSource: записи без привязки к каналу",
                    detail=f"Найдено источников без channel_id: {count}.",
                    why="Модуль, учитывающий каналы, не сможет применить настройки "
                    "к источнику без канала.",
                    how_to_fix="Привяжите источник к каналу в разделе «Content Studio».",
                    subsystem="content",
                )
            )
        return findings

    async def _check_audience_session(self) -> list[Finding]:
        """Warn when audience sources exist but no account can scan them."""
        from sqlalchemy import func, select

        from backend.app.db.models.audience import AudienceSource
        from backend.app.db.models.session import SessionStatus, UserSession

        sources = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(AudienceSource)
                )
            ).scalar_one()
        )
        if not sources:
            return []
        connected = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(UserSession)
                    .where(UserSession.status == SessionStatus.CONNECTED)
                )
            ).scalar_one()
        )
        if connected:
            return []
        return [
            Finding(
                id="audience.session_missing",
                category="integration",
                severity=SEVERITY_WARNING,
                confidence="high",
                title="Источник аудитории подключён, но нет аккаунта для сканирования",
                detail=f"Источников: {sources}, подключённых аккаунтов: 0.",
                why="Сканирование участников требует пользовательского аккаунта.",
                how_to_fix="Подключите аккаунт в разделе «Аккаунты» или используйте "
                "бот-режим там, где он доступен.",
                subsystem="audience",
            )
        ]

    async def _check_reaction_capability(self) -> list[Finding]:
        """Warn when a reaction profile uses emoji the channel does not support."""
        import json

        from sqlalchemy import select

        from backend.app.db.models.capability import CAPABILITY_OK, ChannelCapabilities
        from backend.app.db.models.reaction import ReactionProfile

        findings: list[Finding] = []
        caps_rows = list(
            (await self.session.execute(select(ChannelCapabilities))).scalars().all()
        )
        ok_rows = [r for r in caps_rows if r.status == CAPABILITY_OK]
        if not ok_rows:
            return []
        available: set[str] = set()
        for row in ok_rows:
            try:
                available.update(
                    json.loads(row.bot_reactions or row.available_reactions or "[]")
                )
            except (ValueError, TypeError):
                continue
        if not available:
            return []
        profiles = list(
            (await self.session.execute(select(ReactionProfile))).scalars().all()
        )
        for profile in profiles:
            try:
                allowed = set(json.loads(profile.allowed_emoji or "[]"))
            except (ValueError, TypeError):
                continue
            unknown = sorted(e for e in allowed if e and e not in available)
            if unknown:
                findings.append(
                    Finding(
                        id=f"reaction.capability.{profile.id}",
                        category="capabilities",
                        severity=SEVERITY_WARNING,
                        confidence="medium",
                        title="Профиль реакции использует emoji, которых нет в канале",
                        detail=f"Профиль «{profile.name}»: {', '.join(unknown)}.",
                        why="Telegram принимает только те реакции, что доступны в канале; "
                        "остальные молча игнорируются.",
                        how_to_fix="Откройте «Реакции» и проверьте набор реакций канала, "
                        "затем уберите недоступные emoji из профиля.",
                        subsystem="reactions",
                    )
                )
        return findings

    async def _check_dead_settings(self) -> list[Finding]:
        """Detect settings rows that no module reads (orphan detection).

        Heuristic and low-confidence: the value may be read via a dynamic key.
        """
        from backend.app.db.repositories.settings import SettingRepository

        rows = await SettingRepository(self.session).list_all()
        if not rows:
            return []
        known = _known_setting_keys()
        findings: list[Finding] = []
        for row in rows:
            if row.key not in known:
                findings.append(
                    Finding(
                        id=f"settings.dead.{row.key}",
                        category="settings",
                        severity=SEVERITY_INFO,
                        confidence="low",
                        title="Настройка существует, но, возможно, не используется",
                        detail=f"Ключ: {row.key}.",
                        why="«Мёртвые» настройки затрудняют поддержку и путают пользователя.",
                        how_to_fix="Проверьте, читает ли модуль эту настройку; если нет — удалите.",
                        subsystem="settings",
                    )
                )
        return findings


def _known_setting_keys() -> set[str]:
    """Return setting keys the codebase reads (via services, constants or UI prefs).

    Keys that are read through a module constant (``ui_prefs.SHOW_EXPLANATIONS``,
    ``ui_prefs.LANGUAGE``) or a declared spec map cannot be seen by a literal AST
    scan, so they are listed here to avoid a false "dead setting" finding. Keys
    that no module consumes at all are deliberately **not** listed, so the runtime
    orphan check stays honest (the static ``check_write_only_settings`` covers the
    write-without-read case).
    """
    from backend.app.services.ui_prefs import SHOW_EXPLANATIONS

    return {
        SHOW_EXPLANATIONS,
        # ``language`` is read through ``ui_prefs.LANGUAGE`` and the Settings UI.
        "language",
        # Notification toggles are read through ``notification_service``.
        "notifications_enabled",
        "notification_routing",
        "notification_quiet_enabled",
        "notification_quiet_start",
        "notification_quiet_end",
        "notification_quiet_tz",
        "notification_aggregation",
        "notification_bot_id",
        "notification_group_chat_id",
        # Mini App settings are read through ``miniapp.service``.
        "miniapp_enabled",
        "miniapp_public_url",
    }
