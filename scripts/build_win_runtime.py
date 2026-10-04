#!/usr/bin/env python3
"""Stage a self-contained Windows CPython runtime for the portable build.

Cross-platform: runs on Linux / macOS / Windows. It downloads the official
Python *embeddable* package and the ``win_amd64`` wheels for the pinned runtime
lock, then extracts them flat into ``<runtime>/site-packages`` so ``run.bat``
works with no Python, Node or Docker installed (decision D-040).

Usage:
    python scripts/build_win_runtime.py <runtime_dir> [options]

Options:
    --app-rel PATH        relative app path for the ._pth (default: ../app)
    --python-version X.Y.Z  embeddable version (default: 3.12.7)
    --arch ARCH           amd64 (default) | win32 | arm64
    --lock FILE           pinned requirements (default: scripts/win-requirements.lock)
    --no-deps             stage only CPython (skip wheel download/extraction)
    --dry-run             print the plan, do not download or write

The lock deliberately excludes ``pyaes`` (a Telethon dependency that ships as an
sdist only, on every platform). This script downloads that sdist separately and
extracts its pure-Python ``pyaes`` package into ``site-packages`` — no compiler
is needed because it is pure Python.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _log(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def _download(url: str, dest: Path) -> None:
    _log(f"Downloading {url}")
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)


def _run(cmd: list[str]) -> None:
    _log(" ".join(cmd))
    subprocess.run(cmd, check=True)


def _extract_wheel(wheel: Path, target: Path) -> None:
    with zipfile.ZipFile(wheel) as zf:
        zf.extractall(target)


def _extract_pyaes(sdist: Path, target: Path) -> None:
    with tarfile.open(sdist) as tf:
        members = [m for m in tf.getmembers() if "/pyaes/" in f"/{m.name}"]
        for member in members:
            parts = Path(member.name).parts
            idx = parts.index("pyaes")
            member.name = str(Path(*parts[idx:]))
            tf.extract(member, target, filter="data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_dir", type=Path)
    parser.add_argument("--app-rel", default="../app")
    parser.add_argument("--python-version", default="3.12.7")
    parser.add_argument("--arch", default="amd64")
    parser.add_argument("--lock", type=Path, default=ROOT / "scripts" / "win-requirements.lock")
    parser.add_argument("--no-deps", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    runtime = args.runtime_dir.resolve()
    version = args.python_version
    pyxy = "".join(version.split(".")[:2])
    zip_name = f"python-{version}-embed-{args.arch}.zip"
    url = os.environ.get(
        "EMBED_URL", f"https://www.python.org/ftp/python/{version}/{zip_name}"
    )
    pth = runtime / f"python{pyxy}._pth"

    _log(f"Runtime dir : {runtime}")
    _log(f"Python      : {version} ({args.arch})")
    _log(f"Lock file   : {args.lock}")

    if args.dry_run:
        _log(f"Would download {url} and unzip into {runtime}")
        _log(f"Would write {pth} (app-rel={args.app_rel}, site-packages)")
        if not args.no_deps:
            _log(f"Would download win wheels from {args.lock} and extract flat")
        return 0

    runtime.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        embed = tmpdir / zip_name
        _download(url, embed)
        _log("Extracting embeddable CPython")
        with zipfile.ZipFile(embed) as zf:
            zf.extractall(runtime)

        pth.write_text(
            f"python{pyxy}.zip\n.\n{args.app_rel}\nsite-packages\nimport site\n",
            encoding="utf-8",
        )
        _log(f"Wrote {pth}")

        if args.no_deps:
            _log("--no-deps: skipping wheel download")
            return 0

        site = runtime / "site-packages"
        site.mkdir(exist_ok=True)
        wheels = tmpdir / "wheels"
        wheels.mkdir()

        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--dest",
                str(wheels),
                "--platform",
                "win_amd64",
                "--python-version",
                pyxy,
                "--abi",
                f"cp{pyxy}",
                "--implementation",
                "cp",
                "--only-binary=:all:",
                "--no-deps",
                "--no-cache-dir",
                "-r",
                str(args.lock),
            ]
        )
        # pyaes ships as an sdist only (pure Python, no compiler needed).
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--dest",
                str(wheels),
                "--no-deps",
                "--no-binary=:all:",
                "--no-cache-dir",
                "pyaes",
            ]
        )

        _log("Extracting wheels into site-packages")
        for wheel in sorted(wheels.glob("*.whl")):
            _extract_wheel(wheel, site)
        for sdist in sorted(wheels.glob("pyaes-*.tar.gz")):
            _extract_pyaes(sdist, site)

    _log(f"Windows runtime staged at {runtime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
