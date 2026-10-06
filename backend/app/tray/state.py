"""Tray Agent state file (v1.4).

The tray agent is a separate process from the backend, so the Web UI cannot see
its live objects. The agent writes a tiny, secret-free JSON snapshot to
``data/tray.json`` (state, pid, restarts, last error); the backend reads it to
show the tray status in Diagnostics. No token, session or personal data is ever
written here.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

from backend.app.core import paths

STATE_FILENAME = "tray.json"


@dataclass(slots=True)
class TraySnapshot:
    """A snapshot of the tray agent's view of the backend process."""

    state: str = "stopped"
    state_title: str = "Остановлено"
    pid: int = 0
    running: bool = False
    auto_restart: bool = True
    restarts_last_hour: int = 0
    last_error: str = ""
    base_url: str = ""
    autostart: bool = False
    version: str = ""
    updated_at: float = 0.0
    extra: dict[str, object] = field(default_factory=dict)


def state_path():  # type: ignore[no-untyped-def]
    return paths.data_dir() / STATE_FILENAME


def write_snapshot(snapshot: TraySnapshot) -> None:
    """Persist a snapshot (best effort; never raises into the agent loop)."""
    try:
        path = state_path()
        path.write_text(
            json.dumps(asdict(snapshot), ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        return


def read_snapshot() -> TraySnapshot:
    """Read the last snapshot, or a safe default when none exists."""
    try:
        path = state_path()
        if not path.is_file():
            return TraySnapshot()
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return TraySnapshot()
    known = set(TraySnapshot.__dataclass_fields__)  # type: ignore[attr-defined]
    filtered = {k: v for k, v in data.items() if k in known}
    return TraySnapshot(**filtered)  # type: ignore[arg-type]


def clear_snapshot() -> None:
    try:
        state_path().unlink(missing_ok=True)
    except OSError:
        return


def pid_alive(pid: int) -> bool:
    """Best-effort check whether a process id is alive (no signals sent)."""
    if pid <= 0:
        return False
    if os.name == "nt":  # pragma: no cover - Windows only
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


__all__ = [
    "STATE_FILENAME",
    "TraySnapshot",
    "clear_snapshot",
    "pid_alive",
    "read_snapshot",
    "state_path",
    "write_snapshot",
]
