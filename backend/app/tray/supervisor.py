"""Backend supervisor used by the TCMS Tray Agent (v1.4).

The supervisor owns the backend *process*: it starts it hidden, waits for real
readiness (``/health``), reports its state, restarts it after an unexpected exit
and enforces a bounded restart rate so a crash cannot become a restart storm.

The heavy parts (subprocess creation, the HTTP health probe) are injected so the
whole supervisor is unit-testable on any platform without spawning a real server
or opening a socket. The Windows-specific "no console window" flag is applied
only on Windows; everywhere else the supervisor runs normally.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from backend.app.core.logging import get_logger

logger = get_logger(__name__)

#: How many restarts are allowed inside the sliding window before the supervisor
#: refuses to restart again (restart-storm protection).
DEFAULT_MAX_RESTARTS_PER_HOUR = 5
_RESTART_WINDOW_SECONDS = 3600.0


class SupervisorState(StrEnum):
    """Lifecycle state of the supervised backend."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"          # exited unexpectedly
    RESTART_LIMIT = "restart_limit"  # too many restarts; manual action needed
    STOPPING = "stopping"


STATE_TITLES = {
    SupervisorState.STOPPED: "Остановлено",
    SupervisorState.STARTING: "Запускается",
    SupervisorState.RUNNING: "Работает",
    SupervisorState.CRASHED: "Основной процесс неожиданно завершился",
    SupervisorState.RESTART_LIMIT: "Слишком частые перезапуски",
    SupervisorState.STOPPING: "Останавливается",
}


@dataclass(slots=True)
class SupervisorConfig:
    """Everything the supervisor needs to start and probe the backend."""

    python: str = field(default_factory=lambda: sys.executable)
    module: str = "backend.app.main"
    host: str = "127.0.0.1"
    port: int = 8000
    cwd: str = ""
    startup_timeout: float = 30.0
    poll_interval: float = 0.4
    auto_restart: bool = True
    max_restarts_per_hour: int = DEFAULT_MAX_RESTARTS_PER_HOUR
    env: dict[str, str] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def health_url(self) -> str:
        return f"{self.base_url}/health"


def _hidden_popen_kwargs() -> dict[str, object]:
    """Return subprocess kwargs that keep the backend window hidden.

    On Windows this suppresses the console window; on other platforms it is a
    no-op so the supervisor still runs for tests and development.
    """
    if os.name == "nt":  # pragma: no cover - Windows only
        creationflags = 0
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        return {"creationflags": creationflags, "startupinfo": startupinfo}
    return {}


def default_spawn(config: SupervisorConfig) -> subprocess.Popen[bytes]:
    """Spawn the backend process (hidden on Windows)."""
    env = {**os.environ, **config.env}
    cmd = [config.python, "-m", config.module]
    return subprocess.Popen(
        cmd,
        cwd=config.cwd or None,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        **_hidden_popen_kwargs(),
    )


def default_health_check(url: str, timeout: float = 2.0) -> bool:
    """Return True when the backend answers ``/health`` with 200/ok."""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if getattr(resp, "status", 0) != 200:
                return False
            body = json.loads(resp.read().decode("utf-8") or "{}")
            return body.get("status") == "ok"
    except Exception:
        return False


class BackendSupervisor:
    """Start, probe, restart and stop the backend process."""

    def __init__(
        self,
        config: SupervisorConfig | None = None,
        *,
        spawn: Callable[[SupervisorConfig], subprocess.Popen[bytes]] | None = None,
        health_check: Callable[[str], bool] | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or SupervisorConfig()
        self._spawn = spawn or default_spawn
        self._health_check = health_check or default_health_check
        self._now = now or time.monotonic
        self._process: subprocess.Popen[bytes] | None = None
        self.state = SupervisorState.STOPPED
        self.last_error = ""
        self._restart_times: deque[float] = deque()
        self._stopping = False

    # --- process helpers -----------------------------------------------------
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _record_restart(self) -> None:
        self._restart_times.append(self._now())
        cutoff = self._now() - _RESTART_WINDOW_SECONDS
        while self._restart_times and self._restart_times[0] < cutoff:
            self._restart_times.popleft()

    def restart_allowed(self) -> bool:
        """True when the restart budget for the last hour is not exhausted."""
        cutoff = self._now() - _RESTART_WINDOW_SECONDS
        recent = [t for t in self._restart_times if t >= cutoff]
        return len(recent) < self.config.max_restarts_per_hour

    # --- lifecycle -----------------------------------------------------------
    def start(self) -> bool:
        """Start the backend process. Returns True when it was spawned."""
        if self.is_running():
            return True
        self._stopping = False
        self.state = SupervisorState.STARTING
        try:
            self._process = self._spawn(self.config)
        except Exception as exc:  # pragma: no cover - environment dependent
            self.last_error = str(exc)
            self.state = SupervisorState.CRASHED
            logger.error("Could not start backend: %s", exc)
            return False
        return True

    async def wait_ready(self, timeout: float | None = None) -> bool:
        """Poll ``/health`` until ready or the timeout expires (no fixed sleep)."""
        deadline = self._now() + (timeout if timeout is not None else self.config.startup_timeout)
        while self._now() < deadline:
            if not self.is_running():
                # The process died during startup.
                self.state = SupervisorState.CRASHED
                self.last_error = "Основной процесс завершился во время запуска."
                return False
            if self._health_check(self.config.health_url):
                self.state = SupervisorState.RUNNING
                self.last_error = ""
                return True
            await asyncio.sleep(self.config.poll_interval)
        self.last_error = "Приложение не успело запуститься вовремя."
        return False

    def stop(self, *, timeout: float = 10.0) -> None:
        """Stop the backend gracefully, then force-kill if it does not exit."""
        self._stopping = True
        self.state = SupervisorState.STOPPING
        proc = self._process
        if proc is None:
            self.state = SupervisorState.STOPPED
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except Exception:
                proc.kill()
        finally:
            self._process = None
            self.state = SupervisorState.STOPPED

    async def restart(self) -> bool:
        """Stop then start again, honouring the restart budget."""
        self.stop()
        if not self.restart_allowed():
            self.state = SupervisorState.RESTART_LIMIT
            self.last_error = (
                "Слишком много перезапусков за последний час. "
                "Проверьте журнал и запустите вручную."
            )
            return False
        self._record_restart()
        started = self.start()
        if started:
            return await self.wait_ready()
        return False

    def check_alive(self) -> SupervisorState:
        """Detect an unexpected exit and update the state accordingly.

        Called by the tray loop. Returns the (possibly updated) state. A graceful
        stop does not flip to CRASHED.
        """
        if self._process is not None and self._process.poll() is not None:
            code = self._process.returncode
            self._process = None
            if self._stopping:
                self.state = SupervisorState.STOPPED
            else:
                self.state = SupervisorState.CRASHED
                self.last_error = (
                    f"Основной процесс неожиданно завершился (код {code})."
                )
                logger.warning("Backend exited unexpectedly with code %s", code)
        return self.state

    async def handle_crash(self) -> bool:
        """React to a crash: restart if allowed, else report the restart limit."""
        if not self.config.auto_restart:
            return False
        if not self.restart_allowed():
            self.state = SupervisorState.RESTART_LIMIT
            self.last_error = (
                "Автоматические перезапуски приостановлены: слишком много сбоев. "
                "Проверьте журнал и запустите вручную."
            )
            return False
        self._record_restart()
        self.state = SupervisorState.STARTING
        if not self.start():
            return False
        return await self.wait_ready()

    def status(self) -> dict[str, object]:
        """Plain-language status for the tray menu and the API."""
        return {
            "state": str(self.state),
            "state_title": STATE_TITLES.get(self.state, str(self.state)),
            "running": self.is_running(),
            "auto_restart": self.config.auto_restart,
            "restart_allowed": self.restart_allowed(),
            "restarts_last_hour": len(self._restart_times),
            "last_error": self.last_error,
            "base_url": self.config.base_url,
        }


__all__ = [
    "DEFAULT_MAX_RESTARTS_PER_HOUR",
    "STATE_TITLES",
    "BackendSupervisor",
    "SupervisorConfig",
    "SupervisorState",
    "default_health_check",
    "default_spawn",
]
