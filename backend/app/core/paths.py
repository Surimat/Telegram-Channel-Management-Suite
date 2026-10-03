"""Filesystem path resolution for predictable runtime directories.

All mutable state lives in known directories so that portable mode can keep
everything relative to the extracted application folder:

    data/  sessions/  backups/  logs/  exports/

Resolution order for the project root:
1. ``TCMS_ROOT`` environment variable (used by portable launch scripts).
2. Auto-detected: walk up from this file until a directory containing
   ``backend/`` and ``.env.example`` is found.
3. Fall back to the current working directory.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Directory names that hold mutable state.
DATA_DIRNAME = "data"
SESSIONS_DIRNAME = "sessions"
BACKUPS_DIRNAME = "backups"
LOGS_DIRNAME = "logs"
EXPORTS_DIRNAME = "exports"
MODELS_DIRNAME = "models"


def _detect_project_root() -> Path:
    env_root = os.environ.get("TCMS_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = Path(__file__).resolve()
    # backend/app/core/paths.py -> project root is 4 parents up.
    candidate = here.parents[3]
    if (candidate / "backend").is_dir():
        return candidate
    # Fall back to CWD (e.g. when installed differently).
    return Path.cwd().resolve()


@lru_cache(maxsize=1)
def project_root() -> Path:
    """Return the absolute project root directory."""
    return _detect_project_root()


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    return _ensure(project_root() / DATA_DIRNAME)


def sessions_dir() -> Path:
    return _ensure(project_root() / SESSIONS_DIRNAME)


def backups_dir() -> Path:
    return _ensure(project_root() / BACKUPS_DIRNAME)


def logs_dir() -> Path:
    return _ensure(project_root() / LOGS_DIRNAME)


def exports_dir() -> Path:
    return _ensure(project_root() / EXPORTS_DIRNAME)


def models_dir() -> Path:
    return _ensure(project_root() / MODELS_DIRNAME)


def static_dir() -> Path:
    """Directory that FastAPI serves the built SPA from."""
    return _ensure(project_root() / "backend" / "app" / "static")


def is_writable(path: Path) -> bool:
    """Return True if ``path`` (a directory) is writable."""
    try:
        return path.is_dir() and os.access(path, os.W_OK)
    except OSError:
        return False
