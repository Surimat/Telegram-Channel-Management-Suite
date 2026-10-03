"""Portable startup smoke test (PHASE 10).

Runs the *real* application in a subprocess with ``TCMS_ROOT`` pointing at a
throwaway directory, exactly like the portable launcher does, then verifies:

* the server becomes healthy on the expected local port;
* mutable directories (data/, sessions/, backups/, logs/, exports/) are created
  under that root, not somewhere else;
* a graceful shutdown via the local endpoint stops the process cleanly.

This exercises the true startup path (lifespan, DB init, SPA mount), not mocks.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_healthy(base_url: str, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/health", timeout=2.0)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


@pytest.mark.slow
def test_portable_startup_and_graceful_shutdown(tmp_path: Path) -> None:
    port = _free_port()
    root = tmp_path / "portable"
    root.mkdir()

    env = {
        **os.environ,
        "TCMS_ROOT": str(root),
        "APP_ENV": "test",
        "APP_HOST": "127.0.0.1",
        "APP_PORT": str(port),
        "APP_SECRET_KEY": "portable-smoke-secret-0123456789",
        "DATABASE_URL": f"sqlite+aiosqlite:///{root / 'data' / 'app.db'}",
        "SCHEDULER_ENABLED": "false",
        "OFFLINE_MODE": "true",
        "PYTHONPATH": str(REPO_ROOT),
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.app.main"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        assert _wait_healthy(base_url), "server did not become healthy in time"

        # Mutable state must live under the portable root.
        for name in ("data", "sessions", "backups", "logs", "exports"):
            assert (root / name).is_dir(), f"missing runtime dir: {name}"
        assert (root / "data" / "app.db").is_file()

        # Graceful shutdown via the local endpoint.
        resp = httpx.post(f"{base_url}/api/v1/system/shutdown", timeout=5.0)
        assert resp.status_code == 200
        proc.wait(timeout=20)
        assert proc.returncode == 0, f"unclean exit: {proc.returncode}"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
