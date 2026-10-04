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
import re
import socket
import subprocess
import sys
import time
import zipfile
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


def _run_helper(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "fetch_embedded_python.sh"), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def test_fetch_embedded_python_dry_run(tmp_path: Path) -> None:
    """The runtime fetcher plans a correct embeddable-Python layout offline."""
    runtime = tmp_path / "runtime"
    result = _run_helper(
        [str(runtime), "--version", "3.12.7", "--dry-run"],
    )
    assert result.returncode == 0, result.stderr
    assert "python-3.12.7-embed-amd64.zip" in result.stdout
    assert "python312._pth" in result.stdout
    assert "../app" in result.stdout
    assert "site-packages" in result.stdout
    # Dry run must not touch the filesystem or the network.
    assert not runtime.exists()


def test_fetch_embedded_python_requires_runtime_dir() -> None:
    result = _run_helper([])
    assert result.returncode == 2
    assert "runtime_dir" in result.stderr


def test_fetch_embedded_python_skip_env() -> None:
    result = _run_helper(["/tmp/ignored-runtime"], env={"SKIP_RUNTIME": "1"})
    assert result.returncode == 0
    assert "not fetching" in result.stdout


def test_fetch_embedded_python_no_deps_flag(tmp_path: Path) -> None:
    """--no-deps still plans CPython staging but skips dependency install."""
    runtime = tmp_path / "runtime"
    result = _run_helper(
        [str(runtime), "--version", "3.12.7", "--no-deps", "--dry-run"],
    )
    assert result.returncode == 0, result.stderr
    assert "python-3.12.7-embed-amd64.zip" in result.stdout
    assert "would pip install" not in result.stdout.lower()


def _run_builder(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "build_win_runtime.py"), *args],
        capture_output=True,
        text=True,
    )


def test_build_win_runtime_dry_run(tmp_path: Path) -> None:
    """The cross-platform runtime builder plans a correct layout offline."""
    runtime = tmp_path / "runtime"
    result = _run_builder([str(runtime), "--app-rel", "../app", "--dry-run"])
    assert result.returncode == 0, result.stderr
    assert "python-3.12.7-embed-amd64.zip" in result.stdout
    assert "python312._pth" in result.stdout
    assert "../app" in result.stdout
    assert not runtime.exists(), "dry run must not touch the filesystem"


def test_build_win_runtime_no_deps_dry_run(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    result = _run_builder([str(runtime), "--no-deps", "--dry-run"])
    assert result.returncode == 0, result.stderr
    assert "would download win wheels" not in result.stdout.lower()


def test_build_portable_stages_offline_tree(tmp_path: Path) -> None:
    """build_portable.sh (offline: no runtime, no npm, no zip) produces the tree."""
    out = tmp_path / "TCMS"
    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts" / "build_portable.sh"),
            str(out),
            "--no-runtime",
            "--no-zip",
            "--no-frontend",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    # Launchers, app code and the mutable-state directories must all be present.
    for name in ("run.bat", "stop.bat", "README.txt", ".env.example"):
        assert (out / name).is_file(), f"missing {name}"
    for name in ("data", "sessions", "backups", "logs", "exports", "models"):
        assert (out / name).is_dir(), f"missing runtime dir: {name}"
    assert (out / "app" / "backend" / "app" / "main.py").is_file()
    # A portable tree must never contain secrets or mutable data.
    for pattern in (".env", "*.session", "*.db"):
        assert not list(out.rglob(pattern)), f"portable tree leaked {pattern}"


def test_build_portable_zip_layout(tmp_path: Path) -> None:
    """The versioned ZIP has run.bat at the root and keeps the mutable dirs."""
    dist = tmp_path / "dist"
    out = dist / "TCMS"
    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts" / "build_portable.sh"),
            str(out),
            "--no-runtime",
            "--no-frontend",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    zips = list(dist.glob("*.zip"))
    assert len(zips) == 1, zips
    with zipfile.ZipFile(zips[0]) as zf:
        names = zf.namelist()
    assert "run.bat" in names
    assert "app/backend/app/main.py" in names
    assert "data/" in names and "sessions/" in names
    # The version in the archive name matches the application version.
    version = (REPO_ROOT / "backend" / "app" / "__init__.py").read_text()
    match = re.search(r'__version__ = "([^"]+)"', version)
    assert match and match.group(1) in zips[0].name


def test_build_portable_zip_with_relative_output(tmp_path: Path) -> None:
    """A relative output dir (as CI passes `dist/TCMS`) still writes the ZIP.

    Regression: the ZIP path was built from the relative OUT and then used after
    `cd "$OUT"`, so `zip` tried to write `dist/TCMS/dist/...` and failed with
    "No such file or directory".
    """
    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts" / "build_portable.sh"),
            "rel/TCMS",
            "--no-runtime",
            "--no-frontend",
        ],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    zips = list((tmp_path / "rel").glob("*.zip"))
    assert len(zips) == 1, (zips, result.stdout[-500:])
    assert zips[0].stat().st_size > 0
    with zipfile.ZipFile(zips[0]) as zf:
        assert "run.bat" in zf.namelist()
