"""Tests for the TCMS Tray Agent supervisor (v1.4).

The supervisor is exercised with an injected fake process and a fake health
probe, so no real backend is spawned and no socket is opened. Autostart and the
secret-free state snapshot are tested without touching the Windows registry.
"""

from __future__ import annotations

import json

from backend.app.tray.supervisor import (
    DEFAULT_MAX_RESTARTS_PER_HOUR,
    BackendSupervisor,
    SupervisorConfig,
    SupervisorState,
)


class _FakeProcess:
    """Minimal ``subprocess.Popen`` stand-in with a controllable exit code."""

    def __init__(self, *, alive: bool = True, code: int | None = None) -> None:
        self.pid = 4242
        self._alive = alive
        self.returncode = code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return None if self._alive else self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self._alive = False
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode or 0

    def kill(self) -> None:
        self.killed = True
        self._alive = False
        self.returncode = -9


def _config(**overrides: object) -> SupervisorConfig:
    base = SupervisorConfig(python="python", module="backend.app.main", port=8000)
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


async def test_supervisor_starts_and_reports_ready() -> None:
    proc = _FakeProcess()
    sup = BackendSupervisor(
        _config(), spawn=lambda _cfg: proc, health_check=lambda _url: True
    )
    assert sup.start() is True
    assert sup.is_running() is True
    assert await sup.wait_ready(timeout=1.0) is True
    assert sup.state is SupervisorState.RUNNING
    status = sup.status()
    assert status["running"] is True
    assert status["base_url"] == "http://127.0.0.1:8000"


async def test_supervisor_reports_crash_and_restarts() -> None:
    procs: list[_FakeProcess] = []

    def _spawn(_cfg: SupervisorConfig) -> _FakeProcess:
        proc = _FakeProcess()
        procs.append(proc)
        return proc

    sup = BackendSupervisor(_config(), spawn=_spawn, health_check=lambda _url: True)
    sup.start()
    # Simulate an unexpected exit of the first process.
    procs[0]._alive = False
    procs[0].returncode = 1
    state = sup.check_alive()
    assert state is SupervisorState.CRASHED
    assert "код 1" in sup.last_error
    # Restart is allowed and spawns a fresh process.
    assert await sup.handle_crash() is True
    assert len(procs) == 2


async def test_supervisor_enforces_restart_limit() -> None:
    now = {"t": 1000.0}
    sup = BackendSupervisor(
        _config(max_restarts_per_hour=2),
        spawn=lambda _cfg: _FakeProcess(),
        health_check=lambda _url: True,
        now=lambda: now["t"],
    )
    for _ in range(2):
        sup.start()
        assert await sup.handle_crash() is True
        now["t"] += 1.0
    # Third crash exceeds the budget: no restart, honest limit state.
    assert await sup.handle_crash() is False
    assert sup.state is SupervisorState.RESTART_LIMIT
    assert "перезапуск" in sup.last_error.lower()


async def test_supervisor_no_auto_restart_when_disabled() -> None:
    sup = BackendSupervisor(
        _config(auto_restart=False),
        spawn=lambda _cfg: _FakeProcess(),
        health_check=lambda _url: True,
    )
    sup.start()
    assert await sup.handle_crash() is False


def test_supervisor_stop_is_not_a_crash() -> None:
    proc = _FakeProcess()
    sup = BackendSupervisor(_config(), spawn=lambda _cfg: proc, health_check=lambda _url: True)
    sup.start()
    sup.stop()
    assert proc.terminated is True
    assert sup.state is SupervisorState.STOPPED
    # check_alive after a graceful stop must not flip to CRASHED.
    assert sup.check_alive() is SupervisorState.STOPPED


def test_supervisor_start_failure_is_reported() -> None:
    def _boom(_cfg: SupervisorConfig) -> _FakeProcess:
        raise OSError("no python")

    sup = BackendSupervisor(_config(), spawn=_boom, health_check=lambda _url: True)
    assert sup.start() is False
    assert sup.state is SupervisorState.CRASHED
    assert "no python" in sup.last_error


def test_restart_budget_window_expires() -> None:
    now = {"t": 0.0}
    sup = BackendSupervisor(
        _config(max_restarts_per_hour=1),
        spawn=lambda _cfg: _FakeProcess(),
        health_check=lambda _url: True,
        now=lambda: now["t"],
    )
    sup._record_restart()
    assert sup.restart_allowed() is False
    # After the one-hour window the budget is free again.
    now["t"] = 3601.0
    assert sup.restart_allowed() is True
    assert DEFAULT_MAX_RESTARTS_PER_HOUR == 5


# --- autostart + state snapshot ---------------------------------------------


def test_autostart_roundtrip_uses_injected_base(tmp_path) -> None:
    from backend.app.tray import autostart

    target = str(tmp_path / "run.bat")
    assert autostart.autostart_enabled(base=tmp_path) is False

    created = autostart.enable_autostart(target, base=tmp_path)
    assert created is not None
    assert created.is_file()
    assert autostart.autostart_enabled(base=tmp_path) is True
    body = created.read_text(encoding="utf-8")
    assert target in body
    assert "--tray" in body
    # No console window: a VBScript launcher with a hidden-window run, never the
    # old `start /min` (which still flashes a minimized console).
    assert '", 0, False' in body
    assert 'start "" /min' not in body
    assert "/min cmd" not in body
    # The launcher only references the program path; no secrets are written.
    assert "token" not in body.lower()

    assert autostart.disable_autostart(base=tmp_path) is True
    assert autostart.autostart_enabled(base=tmp_path) is False


def test_autostart_is_safe_without_startup_dir(monkeypatch) -> None:
    from backend.app.tray import autostart

    monkeypatch.delenv("APPDATA", raising=False)
    assert autostart.startup_dir() is None
    assert autostart.enable_autostart("run.bat") is None
    assert autostart.autostart_enabled() is False


def test_autostart_removes_the_legacy_console_launcher(tmp_path) -> None:
    """Upgrading from the pre-v2.0 ``.cmd`` launcher must not start the app twice."""
    from backend.app.tray import autostart

    legacy = tmp_path / "TCMS Tray Agent.cmd"
    legacy.write_text("start /min run.bat --tray", encoding="utf-8")
    assert autostart.autostart_enabled(base=tmp_path) is True

    autostart.enable_autostart(str(tmp_path / "run.bat"), base=tmp_path)
    assert not legacy.exists()  # the old entry is gone
    assert (tmp_path / "TCMS Tray Agent.vbs").is_file()

    # A leftover legacy file is also reported and cleared by disable.
    legacy.write_text("start /min run.bat --tray", encoding="utf-8")
    assert autostart.autostart_enabled(base=tmp_path) is True
    assert autostart.disable_autostart(base=tmp_path) is True
    assert not legacy.exists()
    assert autostart.autostart_enabled(base=tmp_path) is False


def test_snapshot_roundtrip_and_pid_check(tmp_path, monkeypatch) -> None:
    from backend.app.tray import state

    monkeypatch.setattr(state, "state_path", lambda: tmp_path / "tray.json")
    snapshot = state.TraySnapshot(
        state="running",
        state_title="Работает",
        pid=4242,
        running=True,
        auto_restart=True,
        restarts_last_hour=0,
        last_error="",
        base_url="http://127.0.0.1:8000",
        autostart=False,
        updated_at=1.0,
    )
    state.write_snapshot(snapshot)
    loaded = state.read_snapshot()
    assert loaded.state == "running"
    assert loaded.pid == 4242
    assert loaded.base_url == "http://127.0.0.1:8000"
    # Unknown keys are ignored, not fatal.
    (tmp_path / "tray.json").write_text(
        json.dumps({"state": "running", "bogus": 1}), encoding="utf-8"
    )
    assert state.read_snapshot().state == "running"
    state.clear_snapshot()
    assert state.read_snapshot().state == "stopped"


def test_snapshot_never_contains_secrets(tmp_path, monkeypatch) -> None:
    from backend.app.tray import state

    monkeypatch.setattr(state, "state_path", lambda: tmp_path / "tray.json")
    state.write_snapshot(state.TraySnapshot(state="running", state_title="Работает"))
    raw = (tmp_path / "tray.json").read_text(encoding="utf-8").lower()
    for forbidden in ("token", "api_hash", "session", "password", "auth_key"):
        assert forbidden not in raw
