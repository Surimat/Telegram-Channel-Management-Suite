"""Windows autostart for the TCMS Tray Agent (v1.4).

"Запускать вместе с Windows" creates (or removes) a shortcut in the current
user's Startup folder — no Administrator rights and no Windows Service for the
portable build. The implementation is dependency-free:

* On Windows it writes a small ``.cmd`` launcher into the Startup folder (the
  same approach as a shortcut, but with no COM dependency). It is only created
  when the owner turns the option on; turning it off deletes the file.
* On other platforms the functions are safe no-ops so the code and its tests run
  everywhere.

The Startup folder is resolved from ``APPDATA``; tests inject a base directory so
nothing outside the temporary tree is ever touched.
"""

from __future__ import annotations

import os
from pathlib import Path

#: File name of the autostart launcher inside the Startup folder.
AUTOSTART_FILENAME = "TCMS Tray Agent.cmd"


def startup_dir(base: Path | None = None) -> Path | None:
    """Return the current user's Startup folder, or ``None`` when unavailable.

    ``base`` lets tests point at a temporary directory instead of the real
    profile. When ``base`` is given it is used verbatim (no OS check), so the
    logic is testable on any platform.
    """
    if base is not None:
        return base
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_shortcut_path(base: Path | None = None) -> Path | None:
    """Return the full path of the autostart launcher (or ``None``)."""
    directory = startup_dir(base)
    if directory is None:
        return None
    return directory / AUTOSTART_FILENAME


def _launcher_body(run_bat: str) -> str:
    """The tiny launcher that starts the tray agent with no console window."""
    return (
        "@echo off\r\n"
        "REM Created by Telegram Channel Management Suite (autostart).\r\n"
        "REM Removing the autostart option deletes this file.\r\n"
        f'start "" /min "{run_bat}" --tray\r\n'
    )


def enable_autostart(run_bat: str, *, base: Path | None = None) -> Path | None:
    """Create the autostart launcher. Returns its path, or ``None`` on failure.

    ``run_bat`` is the portable ``run.bat`` path (or any launcher the owner
    chose). No Administrator rights are required — the Startup folder is
    per-user.
    """
    path = startup_shortcut_path(base)
    if path is None:
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_launcher_body(run_bat), encoding="utf-8")
    except OSError:
        return None
    return path


def disable_autostart(*, base: Path | None = None) -> bool:
    """Remove the autostart launcher. Returns True when it no longer exists."""
    path = startup_shortcut_path(base)
    if path is None:
        return False
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def autostart_enabled(*, base: Path | None = None) -> bool:
    """True when the autostart launcher is present."""
    path = startup_shortcut_path(base)
    if path is None:
        return False
    return path.is_file()


__all__ = [
    "AUTOSTART_FILENAME",
    "autostart_enabled",
    "disable_autostart",
    "enable_autostart",
    "startup_dir",
    "startup_shortcut_path",
]
