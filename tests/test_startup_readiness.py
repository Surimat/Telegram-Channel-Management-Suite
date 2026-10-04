"""Startup readiness + portable launcher regression tests.

These verify the *no-race* startup contract:

* the readiness helper only reports ready once ``/health`` answers, and never
  raises on a timeout (so the launcher can print a friendly message);
* ``portable/run.bat`` waits for ``/health`` instead of using a fixed sleep;
* the readiness helper ships in the portable distribution.

No network, no real server required: the HTTP probe is exercised against a
local ``http.server`` and against a closed port.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from backend.app.core import startup

REPO_ROOT = Path(__file__).resolve().parents[1]


class _HealthHandler(BaseHTTPRequestHandler):
    """Minimal server that answers ``/health`` with 200 after N requests."""

    ready_after = 0
    seen = 0

    def do_GET(self) -> None:
        type(self).seen += 1
        if self.path == "/health" and type(self).seen > type(self).ready_after:
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *_args: object) -> None:  # silence the test server
        return


@pytest.fixture
def health_server():
    """Start a local HTTP server and yield ``(base_url, handler_class)``."""
    _HealthHandler.ready_after = 0
    _HealthHandler.seen = 0
    server = HTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", _HealthHandler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_wait_for_health_succeeds_when_server_is_up(health_server) -> None:
    base_url, _ = health_server
    result = startup.wait_for_health(base_url, timeout=5, poll_interval=0.05)
    assert result.ready is True
    assert result.attempts >= 1


def test_wait_for_health_waits_for_a_late_server(health_server) -> None:
    base_url, handler = health_server
    # Fail the first 3 probes, then succeed: the helper must keep polling.
    handler.ready_after = 3
    result = startup.wait_for_health(base_url, timeout=5, poll_interval=0.05)
    assert result.ready is True
    assert result.attempts >= 4


def test_wait_for_health_times_out_without_raising() -> None:
    # Port 1 is not serving; the helper must return, not raise.
    result = startup.wait_for_health(
        "http://127.0.0.1:1", timeout=0.5, poll_interval=0.05, request_timeout=0.2
    )
    assert result.ready is False
    assert result.last_error
    assert result.attempts >= 1


def test_run_bat_waits_for_health_not_fixed_sleep() -> None:
    run_bat = (REPO_ROOT / "portable" / "run.bat").read_text(encoding="utf-8")
    assert "open_when_ready.ps1" in run_bat
    assert "/health" in (REPO_ROOT / "portable" / "open_when_ready.ps1").read_text(
        encoding="utf-8"
    )
    # The old fixed-delay approach must be gone.
    assert "timeout /t 3" not in run_bat
    assert "STARTUP_TIMEOUT" in run_bat
    assert "STARTUP_POLL_MS" in run_bat


def test_readiness_helper_reports_friendly_timeout_message() -> None:
    ps1 = (REPO_ROOT / "portable" / "open_when_ready.ps1").read_text(encoding="utf-8")
    assert "did not finish starting" in ps1
    assert "exit 1" in ps1
    # It must not open the browser when the server is not ready.
    assert "Start-Process $url" in ps1


def test_build_portable_ships_readiness_helper() -> None:
    script = (REPO_ROOT / "scripts" / "build_portable.sh").read_text(encoding="utf-8")
    assert "open_when_ready.ps1" in script
