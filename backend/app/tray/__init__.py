"""TCMS Tray Agent (v1.4).

A very light supervisor/background process so the portable app feels like a
normal Windows application instead of a console window:

* starts the backend **hidden** (no console window),
* waits for ``/health`` (never a fixed sleep),
* shows a tray icon with a context menu (start/stop/restart/diagnostics/update),
* detects an unexpected backend exit and can restart it with a bounded backoff,
* optionally registers itself in the Windows Startup folder (no admin needed).

The package imports nothing heavy: no AI, no Telethon, no FFmpeg. The tray icon
uses ``pystray`` only if it is installed; otherwise the supervisor still runs and
the agent degrades gracefully (see :mod:`backend.app.tray.agent`).
"""

from __future__ import annotations

from backend.app.tray.autostart import (
    autostart_enabled,
    disable_autostart,
    enable_autostart,
    startup_shortcut_path,
)
from backend.app.tray.supervisor import (
    BackendSupervisor,
    SupervisorConfig,
    SupervisorState,
)

__all__ = [
    "BackendSupervisor",
    "SupervisorConfig",
    "SupervisorState",
    "autostart_enabled",
    "disable_autostart",
    "enable_autostart",
    "startup_shortcut_path",
]
