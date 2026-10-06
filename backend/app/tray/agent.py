"""Tray Agent entry point (v1.4).

Runs the supervisor and, when ``pystray`` is available, shows a tray icon with a
context menu (open Web UI / diagnostics / restart / stop / start / check for
updates / autostart / exit). If ``pystray`` is not installed the agent still
supervises the backend in a headless loop, so the portable app never depends on
an optional GUI package to keep the backend running.

The agent imports no AI/Telethon/FFmpeg code: it only controls the backend
process and its health.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import webbrowser

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger, setup_logging
from backend.app.tray.autostart import (
    autostart_enabled,
    disable_autostart,
    enable_autostart,
)
from backend.app.tray.supervisor import BackendSupervisor, SupervisorConfig

logger = get_logger(__name__)


def _build_config(*, python: str = "") -> SupervisorConfig:
    settings = get_settings()
    import sys

    return SupervisorConfig(
        python=python or sys.executable,
        host=settings.app_host,
        port=settings.app_port,
        auto_restart=True,
    )


def build_supervisor(*, python: str = "") -> BackendSupervisor:
    """Build a supervisor for the current install."""
    return BackendSupervisor(_build_config(python=python))


def open_web_ui(supervisor: BackendSupervisor) -> None:
    """Open the local Web UI in the default browser (never a dead page)."""
    with contextlib.suppress(Exception):
        webbrowser.open(supervisor.config.base_url)


def _write_snapshot(supervisor: BackendSupervisor) -> None:
    """Publish the supervisor state so the backend/UI can display it."""
    import time

    from backend.app.tray.autostart import autostart_enabled
    from backend.app.tray.state import TraySnapshot, write_snapshot

    status = supervisor.status()
    write_snapshot(
        TraySnapshot(
            state=str(status["state"]),
            state_title=str(status["state_title"]),
            pid=supervisor._process.pid if supervisor._process is not None else 0,
            running=bool(status["running"]),
            auto_restart=bool(status["auto_restart"]),
            restarts_last_hour=int(status["restarts_last_hour"]),
            last_error=str(status["last_error"]),
            base_url=str(status["base_url"]),
            autostart=autostart_enabled(),
            updated_at=time.time(),
        )
    )


def _run_headless(supervisor: BackendSupervisor, *, open_browser: bool = True) -> int:
    """Supervise the backend without a GUI (fallback when pystray is absent)."""

    async def _loop() -> None:
        if not supervisor.start():
            _write_snapshot(supervisor)
            return
        if await supervisor.wait_ready() and open_browser:
            open_web_ui(supervisor)
        _write_snapshot(supervisor)
        while True:
            await asyncio.sleep(2.0)
            state = supervisor.check_alive()
            if state.value == "crashed":
                await supervisor.handle_crash()
            _write_snapshot(supervisor)

    try:
        asyncio.run(_loop())
    except KeyboardInterrupt:  # pragma: no cover - interactive
        supervisor.stop()
        _write_snapshot(supervisor)
    return 0


def run_tray(*, python: str = "", open_browser: bool = True) -> int:
    """Run the tray agent (GUI when available, headless otherwise)."""
    settings = get_settings()
    setup_logging(settings)
    supervisor = build_supervisor(python=python)

    try:
        import pystray  # type: ignore[import-not-found]
        from pystray import Menu, MenuItem  # type: ignore[import-not-found]
    except Exception:
        logger.info("pystray is not installed; running the supervisor headlessly.")
        return _run_headless(supervisor, open_browser=open_browser)

    def _start(_icon, _item) -> None:  # type: ignore[no-untyped-def]
        threading.Thread(target=lambda: asyncio.run(_start_and_wait()), daemon=True).start()

    async def _start_and_wait() -> None:
        supervisor.start()
        await supervisor.wait_ready()

    def _restart(_icon, _item) -> None:  # type: ignore[no-untyped-def]
        threading.Thread(target=lambda: asyncio.run(supervisor.restart()), daemon=True).start()

    def _stop(_icon, _item) -> None:  # type: ignore[no-untyped-def]
        supervisor.stop()

    def _toggle_autostart(icon, _item) -> None:  # type: ignore[no-untyped-def]
        if autostart_enabled():
            disable_autostart()
        else:
            enable_autostart(str(_run_bat_path()))
        icon.update_menu()

    def _quit(icon, _item) -> None:  # type: ignore[no-untyped-def]
        supervisor.stop()
        icon.stop()

    menu = Menu(
        MenuItem("Открыть Web UI", lambda i, _it: open_web_ui(supervisor)),
        MenuItem("Диагностика", lambda i, _it: _open(supervisor, "/diagnostics")),
        Menu.SEPARATOR,
        MenuItem("Перезапустить", _restart),
        MenuItem("Остановить", _stop),
        MenuItem("Запустить", _start),
        MenuItem("Проверить обновления", lambda i, _it: _open(supervisor, "/system")),
        Menu.SEPARATOR,
        MenuItem(
            "Запускать вместе с Windows",
            _toggle_autostart,
            checked=lambda _item: autostart_enabled(),
        ),
        Menu.SEPARATOR,
        MenuItem("Выход", _quit),
    )

    def _run() -> None:
        import asyncio as _asyncio

        _asyncio.run(_start_and_wait())

    threading.Thread(target=_run, daemon=True).start()
    try:
        pystray.Icon("TCMS", title="Telegram Channel Management Suite", menu=menu).run()
    finally:
        supervisor.stop()
    return 0


def _run_bat_path() -> str:
    from pathlib import Path

    from backend.app.core import paths

    candidate = paths.project_root() / "run.bat"
    if candidate.is_file():
        return str(candidate)
    return str(Path(__file__).resolve())


def _open(supervisor: BackendSupervisor, path: str) -> None:
    with contextlib.suppress(Exception):
        webbrowser.open(supervisor.config.base_url + path)


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    # ``--no-browser`` lets run.bat own the browser launch via the readiness
    # helper, so the page never opens before /health answers.
    open_browser = "--no-browser" not in args
    if "--headless" in args:
        setup_logging(get_settings())
        return _run_headless(build_supervisor(), open_browser=open_browser)
    return run_tray(open_browser=open_browser)


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    raise SystemExit(main())
