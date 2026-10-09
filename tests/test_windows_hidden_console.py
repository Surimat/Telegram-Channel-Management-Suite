"""Windows hidden-console verification for the portable tray start (v2.0).

The portable app must launch with **no console window**. That depends on three
things, each asserted here without needing a real Windows host:

1. the supervisor's spawn kwargs set the no-window creation flags on Windows
   (``CREATE_NO_WINDOW`` + ``STARTF_USESHOWWINDOW``/``SW_HIDE``);
2. the autostart launcher is a ``.cmd``-free VBScript run with window state ``0``;
3. ``portable/run.bat`` prefers the windowless ``pythonw.exe`` interpreter and
   uses ``start /b`` for the tray agent.
"""

from __future__ import annotations

from pathlib import Path

from backend.app.tray import autostart, supervisor

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_supervisor_sets_no_window_flags_on_windows(monkeypatch) -> None:
    """On Windows the backend is spawned with CREATE_NO_WINDOW + SW_HIDE."""
    import subprocess

    class _StartupInfo:
        def __init__(self) -> None:
            self.dwFlags = 0
            self.wShowWindow = -1  # a visible default, must be overwritten

    # Simulate Windows: os.name == "nt" and the subprocess constants present.
    monkeypatch.setattr(supervisor.os, "name", "nt")
    monkeypatch.setattr(subprocess, "STARTUPINFO", _StartupInfo, raising=False)
    monkeypatch.setattr(subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)

    kwargs = supervisor._hidden_popen_kwargs()
    assert kwargs["creationflags"] & 0x08000000  # CREATE_NO_WINDOW
    assert kwargs["creationflags"] & 0x200  # CREATE_NEW_PROCESS_GROUP
    info = kwargs["startupinfo"]
    assert info.dwFlags & 1  # STARTF_USESHOWWINDOW
    assert info.wShowWindow == 0  # SW_HIDE (never a visible window)


def test_hidden_kwargs_are_a_noop_off_windows() -> None:
    """Off Windows the helper must not invent Windows-only kwargs."""
    assert supervisor._hidden_popen_kwargs() == {}


def test_autostart_launcher_hides_the_window(tmp_path) -> None:
    """The autostart entry uses a VBScript ``Run(..., 0, ...)`` hidden launch."""
    body = autostart._launcher_body(r"C:\TCMS\run.bat")
    assert "WScript.Shell" in body
    assert ", 0, False" in body  # window state 0 == hidden, not a visible window
    assert ", 1," not in body
    assert '--tray' in body
    assert not body.lower().startswith("start")  # never a flashing .cmd launch


def test_run_bat_prefers_windowless_interpreter_and_start_b() -> None:
    """The portable launcher prefers pythonw.exe and ``start /b``."""
    bat = (REPO_ROOT / "portable" / "run.bat").read_text(encoding="utf-8", errors="replace")
    assert "pythonw.exe" in bat
    assert 'set "PYTHONW=' in bat
    assert "start" in bat and "/b" in bat
    assert "backend.app.tray.agent" in bat
