"""Operational module registry: the single server-side gate for channel modules.

The Channel Registry stores a per-channel JSON bool map in ``Channel.modules``
(D-051). Until now that map was only *saved* — it did not influence whether a
module actually ran, so an owner could switch a module off on a channel while a
different API method or a durable scheduler job kept working it. This module
makes the map authoritative: every operation that belongs to a channel module
consults :meth:`ChannelModuleGuard.require` (or :meth:`is_enabled`) for the exact
channel before it does any work.

Rules that keep this safe and backward-compatible:

* **Never-configured ⇒ enabled (legacy).** A channel whose ``modules`` map is
  empty predates the "connect modules" toggle (it was added later), so every
  module stays enabled for it — an existing owner is never silently cut off.
* **Configured map is authoritative.** ``ChannelService.set_modules`` always
  persists every :data:`KNOWN_MODULE_IDS` key, so once a channel has a map it
  records an explicit ``false`` for anything switched off (and a missing key in a
  configured map counts as disabled).
* **Explicit ``false`` ⇒ blocked.** A channel whose map says ``{"invites": false}``
  cannot run invites through *any* path (API, scheduler, background task).
* **No channel ⇒ not this module's problem.** A legacy target with no registry
  channel (``""`` / unknown id) has no authority to consult, so the guard stays
  out of the way; other server policies (e.g. the personal-account switch,
  D-123) and Telegram's real permissions still apply.
* **Modules are independent.** The guard reads exactly one channel row, so
  switching a module on one channel never affects another channel.

Enabling a module is **not** the same as Telegram allowing it: real bot rights
and API limits are verified separately (the permission/binding probes). This gate
only answers "did the owner connect this module to this channel?".
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.repositories.channels import ChannelRepository

#: Canonical module ids. Kept in one place so every caller uses the same keys the
#: UI toggles and ``ChannelService`` validate against.
MODULE_REACTIONS = "reactions"
MODULE_AUDIENCE = "audience"
MODULE_INVITES = "invites"
MODULE_ANALYTICS = "analytics"

KNOWN_MODULE_IDS = (
    MODULE_REACTIONS,
    MODULE_AUDIENCE,
    MODULE_INVITES,
    MODULE_ANALYTICS,
)

MODULE_TITLES = {
    MODULE_REACTIONS: "Реакции",
    MODULE_AUDIENCE: "Аудитория",
    MODULE_INVITES: "Приглашения",
    MODULE_ANALYTICS: "Аналитика",
}


class ChannelModuleDisabledError(Exception):
    """A module operation was refused because the channel module is switched off.

    Carries a friendly ``message``, an actionable ``how_to_fix`` and the channel
    it concerns so the API can answer "what happened?" and "how do I fix it?"
    (D-016). It is mapped to HTTP 403 by the API error handler.
    """

    def __init__(
        self,
        module: str,
        *,
        channel_label: str = "",
        channel_id: str = "",
        status_code: int = 403,
    ) -> None:
        title = MODULE_TITLES.get(module, module)
        where = f" для канала «{channel_label}»" if channel_label else ""
        super().__init__(f"Модуль «{title}» отключён{where}.")
        self.module = module
        self.channel_id = channel_id
        self.message = f"Модуль «{title}» отключён{where}."
        self.how_to_fix = (
            f"Включите модуль «{title}» в разделе «Каналы» для этого канала, "
            "чтобы выполнить действие."
        )
        self.status_code = status_code


def parse_modules(raw: object) -> dict[str, bool]:
    """Parse a stored ``Channel.modules`` JSON string into a bool dict."""
    try:
        data = json.loads(raw or "{}")  # type: ignore[arg-type]
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        return {}
    return {str(k): bool(v) for k, v in data.items()}


def _is_configured(modules: dict[str, bool]) -> bool:
    """True once the owner has connected modules for a channel.

    ``set_modules`` always persists every :data:`KNOWN_MODULE_IDS` key, so a
    stored map that contains any known key is an explicit owner choice. An empty
    map means the channel predates the "connect modules" toggle or was never
    configured — that legacy state stays backward-compatible (all enabled).
    """
    return any(name in modules for name in KNOWN_MODULE_IDS)


def effective_modules(modules: dict[str, bool]) -> dict[str, bool]:
    """Resolve the effective enabled-map for the four canonical modules.

    * **Never configured** (no known key): every module stays enabled, so an
      existing owner is not silently cut off when this gate is introduced.
    * **Configured**: the stored values are authoritative; a module key that is
      absent from a configured map counts as disabled.
    """
    if not _is_configured(modules):
        return dict.fromkeys(KNOWN_MODULE_IDS, True)
    return {name: bool(modules.get(name, False)) for name in KNOWN_MODULE_IDS}


def module_enabled(modules: dict[str, bool], module: str) -> bool:
    """Return whether ``module`` is enabled given a channel's module map.

    Never-configured channels treat every module as enabled (legacy); configured
    channels honour the explicit map. Unknown modules are always enabled so this
    gate never blocks a feature it does not know about.
    """
    if module not in KNOWN_MODULE_IDS:
        return True
    return effective_modules(modules)[module]


class ChannelModuleGuard:
    """Reads a channel's module map and enforces it for one module operation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ChannelRepository(session)
        self._cache: dict[str, dict[str, bool] | None] = {}

    async def _modules(self, channel_id: str) -> dict[str, bool] | None:
        """Return the module map for ``channel_id`` or ``None`` when unknown."""
        if not channel_id:
            return None
        if channel_id in self._cache:
            return self._cache[channel_id]
        channel = await self.repo.get(channel_id)
        modules = parse_modules(channel.modules) if channel is not None else None
        self._cache[channel_id] = modules
        return modules

    async def is_enabled(self, channel_id: str, module: str) -> bool:
        """True when ``module`` may run for ``channel_id``.

        An empty/unknown ``channel_id`` (legacy target, no registry link) is not
        blocked here — there is no authoritative channel to consult.
        """
        modules = await self._modules(channel_id)
        if modules is None:
            return True
        return module_enabled(modules, module)

    async def check(self, channel_id: str, module: str) -> str | None:
        """Return the channel label when ``module`` is blocked, else ``None``."""
        if await self.is_enabled(channel_id, module):
            return None
        channel = await self.repo.get(channel_id)
        if channel is None:
            return ""
        return channel.title or channel.reference

    async def require(self, channel_id: str, module: str) -> None:
        """Raise :class:`ChannelModuleDisabledError` when the module is off.

        Call this *before* creating any DB row, session file or provider so a
        refused operation leaves no orphan behind (mirrors D-123).
        """
        label = await self.check(channel_id, module)
        if label is not None:
            raise ChannelModuleDisabledError(
                module, channel_label=label, channel_id=channel_id
            )


__all__ = [
    "KNOWN_MODULE_IDS",
    "MODULE_ANALYTICS",
    "MODULE_AUDIENCE",
    "MODULE_INVITES",
    "MODULE_REACTIONS",
    "MODULE_TITLES",
    "ChannelModuleDisabledError",
    "ChannelModuleGuard",
    "effective_modules",
    "module_enabled",
    "parse_modules",
]
