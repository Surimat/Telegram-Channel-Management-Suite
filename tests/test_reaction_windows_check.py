"""Guard the owner-facing Reaction Manager check for the Windows build (D-130).

The non-programmer owner runs ``CHECK_REACTIONS.bat`` from the portable ZIP; it
calls ``scripts/check_reactions.py`` with the *embedded* Windows Python, which
ships only the application's runtime dependencies — ``pytest`` is **not** among
them. These tests make sure the check stays runnable there and stays bundled:

1. the check script runs to a PASS with ``pytest`` import blocked;
2. the check script never imports ``pytest`` at module level;
3. ``portable/CHECK_REACTIONS.bat`` exists and points at the bundled paths;
4. ``scripts/build_portable.sh`` copies the check script and the launcher.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECK_SCRIPT = ROOT / "scripts" / "check_reactions.py"
LAUNCHER = ROOT / "portable" / "CHECK_REACTIONS.bat"
BUILD = ROOT / "scripts" / "build_portable.sh"

# A tiny sitecustomize-style preamble: install a meta-path finder that makes any
# ``import pytest`` fail, proving the check does not depend on it.
_BLOCK_PYTEST = """
import sys
import importlib.abc


class _BlockPytest(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "pytest" or name.startswith("pytest."):
            raise ImportError("pytest is intentionally blocked (portability guard)")
        return None


sys.meta_path.insert(0, _BlockPytest())
import runpy

runpy.run_path({script!r}, run_name="__main__")
"""


def test_check_script_runs_without_pytest() -> None:
    """The whole check passes even when ``import pytest`` is impossible."""
    preamble = _BLOCK_PYTEST.format(script=str(CHECK_SCRIPT))
    result = subprocess.run(
        [sys.executable, "-c", preamble],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=300,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ИТОГ: ПРОЙДЕНО" in output


def test_check_script_has_no_module_level_pytest_import() -> None:
    """No top-level ``import pytest`` may creep back in (breaks the embedded build)."""
    source = CHECK_SCRIPT.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import pytest", "from pytest")):
            raise AssertionError(f"module-level pytest import: {stripped!r}")


def test_portable_bundles_the_check() -> None:
    """The launcher and the build script ship the check in the ZIP."""
    assert LAUNCHER.is_file(), "portable/CHECK_REACTIONS.bat is missing"
    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    assert "app\\scripts\\check_reactions.py" in launcher_text
    assert "runtime\\python.exe" in launcher_text

    build_text = BUILD.read_text(encoding="utf-8")
    assert "check_reactions.py" in build_text
    assert "CHECK_REACTIONS.bat" in build_text
