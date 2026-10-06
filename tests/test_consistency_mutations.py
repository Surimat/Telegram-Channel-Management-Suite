"""Meta-audit: prove the Consistency Auditor detects *deliberately seeded* drift.

The auditor is only trustworthy if it catches a controlled defect. These tests
build an isolated **copy** of the repository source tree, inject one synthetic
defect per test, and assert the corresponding finding appears — then discard the
copy. Nothing is ever written to the production tree, so the working branch stays
clean and no synthetic defect can leak into a release.

This is the "проверка проверяющего" (audit-the-auditor) suite (D-099). It answers
``DEFECT → EXPECTED FINDING → DETECTED?`` for each seeded defect and is wired into
CI so a silently-broken check fails the build instead of passing green.

The kill-rate summary is produced by ``tests/test_meta_audit.py``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.app.services import consistency_checks as cc
from backend.app.services.consistency_types import SEVERITY_ERROR

REAL_ROOT = Path(cc.ROOT)
_COPY_DIRS = ("backend/app", "frontend/src", "migrations/versions", "docs")


@dataclass
class Sandbox:
    """An isolated copy of the repo source tree with the auditor pointed at it."""

    root: Path

    def run(self) -> list:
        return cc.run_static_checks()

    def ids(self, *, severity: str | None = None) -> set[str]:
        return {
            f.id
            for f in self.run()
            if severity is None or f.severity == severity
        }

    def errors(self) -> set[str]:
        return self.ids(severity=SEVERITY_ERROR)

    def write(self, rel: str, content: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def patch(self, rel: str, old: str, new: str) -> None:
        path = self.root / rel
        text = path.read_text(encoding="utf-8")
        assert old in text, f"patch anchor not found in {rel}: {old!r}"
        path.write_text(text.replace(old, new), encoding="utf-8")

    def append(self, rel: str, extra: str) -> None:
        path = self.root / rel
        path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")

    def delete(self, rel: str) -> None:
        (self.root / rel).unlink()


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Copy the source tree to a temp dir and repoint the auditor at the copy."""
    root = tmp_path / "repo"
    for rel in _COPY_DIRS:
        src = REAL_ROOT / rel
        if not src.is_dir():
            continue
        shutil.copytree(
            src,
            root / rel,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    monkeypatch.setattr(cc, "ROOT", root)
    monkeypatch.setattr(cc, "BACKEND", root / "backend" / "app")
    monkeypatch.setattr(cc, "FRONTEND", root / "frontend" / "src")
    monkeypatch.setattr(cc, "MIGRATIONS", root / "migrations" / "versions")
    monkeypatch.setattr(cc, "DOCS", root / "docs")
    box = Sandbox(root=root)
    # Sanity: the copied tree is clean, so any finding is caused by the defect.
    baseline = box.run()
    assert not [f for f in baseline if f.severity == SEVERITY_ERROR], [
        f.id for f in baseline if f.severity == SEVERITY_ERROR
    ]
    return box


# ---------------------------------------------------------------------------
# A. Broken frontend route
# ---------------------------------------------------------------------------
def test_detects_broken_frontend_route(sandbox: Sandbox) -> None:
    sandbox.append(
        "frontend/src/router.ts",
        "\n  { path: '/ghost', name: 'ghost', "
        "component: () => import('@/views/GhostView.vue') },\n",
    )
    assert "frontend.route.views/GhostView.vue" in sandbox.errors()


# ---------------------------------------------------------------------------
# B. Broken API consumer (frontend calls a non-existent backend area)
# ---------------------------------------------------------------------------
def test_detects_broken_api_consumer(sandbox: Sandbox) -> None:
    sandbox.append("frontend/src/api/client.ts", "\n// uses /api/v1/ghostarea\n")
    assert "api.frontend_unknown" in sandbox.errors()


# ---------------------------------------------------------------------------
# C. Orphan backend endpoint (router never registered)
# ---------------------------------------------------------------------------
def test_detects_orphan_backend_endpoint(sandbox: Sandbox) -> None:
    sandbox.write(
        "backend/app/api/v1/ghostarea.py",
        'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/ghostarea")\n',
    )
    assert "api.router_unregistered.ghostarea" in sandbox.errors()


# ---------------------------------------------------------------------------
# D. Broken scheduler handler
# ---------------------------------------------------------------------------
def test_detects_scheduler_job_without_handler(sandbox: Sandbox) -> None:
    sandbox.write(
        "backend/app/services/zz_ghost_jobs.py",
        '_JOB_KIND = "ghost.job"\n',
    )
    assert "scheduler.job_without_handler" in sandbox.errors()


# ---------------------------------------------------------------------------
# E. Broken provider registry
# ---------------------------------------------------------------------------
def test_detects_missing_fake_provider(sandbox: Sandbox) -> None:
    sandbox.delete("backend/app/providers/fake_audience.py")
    assert "providers.audience.fake_audience.py" in sandbox.errors()


def test_detects_registry_mapping_without_module(sandbox: Sandbox) -> None:
    sandbox.append(
        "backend/app/providers/registry.py",
        "\n\ndef build_ghost():\n"
        "    from backend.app.providers.ghost_provider import Ghost\n"
        "    return Ghost()\n",
    )
    assert "providers.registry_missing.ghost_provider" in sandbox.errors()


# ---------------------------------------------------------------------------
# F. False capability (implemented=True with no real implementation)
# ---------------------------------------------------------------------------
@pytest.fixture
def caps(monkeypatch: pytest.MonkeyPatch):
    """Patch ``cc.CAPABILITIES`` entries in memory (registry is a Python object)."""
    import dataclasses

    original = cc.CAPABILITIES

    def set_implemented(key: str, value: bool) -> None:
        monkeypatch.setattr(
            cc,
            "CAPABILITIES",
            tuple(
                dataclasses.replace(c, implemented=value) if c.key == key else c
                for c in original
            ),
        )

    def set_requires(key: str, requires: tuple[str, ...]) -> None:
        monkeypatch.setattr(
            cc,
            "CAPABILITIES",
            tuple(
                dataclasses.replace(c, requires=requires) if c.key == key else c
                for c in original
            ),
        )

    return set_implemented, set_requires


def test_detects_false_capability(sandbox: Sandbox, caps) -> None:
    # A capability flipped to implemented=True without any implementation signal
    # (no anchor registered) must be an error, not silently trusted.
    set_implemented, _ = caps
    set_implemented("config_sync", True)
    assert "capabilities.no_anchor.config_sync" in sandbox.errors()


def test_detects_capability_whose_service_is_missing(sandbox: Sandbox, caps) -> None:
    # Anchor exists but the service class is gone → the capability is a lie.
    set_implemented, _ = caps
    set_implemented("reaction", True)
    sandbox.delete("backend/app/services/reaction_service.py")
    assert "capabilities.unimplemented.reaction" in sandbox.errors()


def test_false_capability_is_not_masked_by_a_stray_string(sandbox: Sandbox, caps) -> None:
    # A capability must not look "implemented" merely because its name appears
    # somewhere in the tree. Only the real service class anchor counts.
    set_implemented, _ = caps
    set_implemented("reaction", True)
    sandbox.delete("backend/app/services/reaction_service.py")
    sandbox.write(
        "backend/app/services/zz_stray.py",
        "# reaction is coming someday\nclass ReactionService:  # not the real one\n"
        "    pass\n",
    )
    assert "capabilities.unimplemented.reaction" in sandbox.errors()


# ---------------------------------------------------------------------------
# G. Broken capability dependency (A requires an unimplemented B)
# ---------------------------------------------------------------------------
def test_detects_capability_dependency_on_unimplemented(sandbox: Sandbox, caps) -> None:
    _, set_requires = caps
    set_requires("donor_discovery", ("config_sync",))
    assert "capabilities.dep_unimplemented.donor_discovery.config_sync" in sandbox.errors()


# ---------------------------------------------------------------------------
# H. Missing i18n key
# ---------------------------------------------------------------------------
def test_detects_missing_i18n_translation(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The catalog is an imported dict; inject a RU-only key in memory.
    monkeypatch.setitem(cc.i18n.MESSAGES, "ghost.key", {"ru": "Привет"})
    assert "i18n.missing.ghost.key" in sandbox.errors()


# ---------------------------------------------------------------------------
# I. Hardcoded user-facing string (known narrow detector)
# ---------------------------------------------------------------------------
def test_detects_hardcoded_ui_string(sandbox: Sandbox) -> None:
    sandbox.append(
        "frontend/src/views/DashboardView.vue",
        "\n<template><p>Эта функция ещё не реализована</p></template>\n",
    )
    hits = [i for i in sandbox.ids() if i.startswith("ux.hardcoded_string.")]
    assert hits, "hardcoded UI string was not detected"


# ---------------------------------------------------------------------------
# J. Broken help reference
# ---------------------------------------------------------------------------
def test_detects_missing_help_topic(sandbox: Sandbox) -> None:
    sandbox.append(
        "frontend/src/views/DashboardView.vue",
        '\n<template><InfoHint topic="ghost_topic" /></template>\n',
    )
    assert "help.missing_topic" in sandbox.errors()


# ---------------------------------------------------------------------------
# K. Model / migration drift
# ---------------------------------------------------------------------------
def test_detects_model_without_migration(sandbox: Sandbox) -> None:
    sandbox.write(
        "backend/app/db/models/ghost.py",
        "from backend.app.db.base import Base\n\n\n"
        'class Ghost(Base):\n    __tablename__ = "ghost_table"\n',
    )
    assert "db.model_without_migration" in sandbox.errors()


def test_detects_column_without_migration(sandbox: Sandbox) -> None:
    # A new column on an existing model has no migration → the migration check
    # must still fire (the table itself is already covered).
    sandbox.write(
        "backend/app/db/models/ghost2.py",
        "from sqlalchemy import String\nfrom sqlalchemy.orm import Mapped, mapped_column\n\n"
        "from backend.app.db.base import Base\n\n\n"
        "class Ghost2(Base):\n"
        '    __tablename__ = "ghost2_table"\n'
        '    name: Mapped[str] = mapped_column(String(32), default="", nullable=False)\n',
    )
    assert "db.model_without_migration" in sandbox.errors()


# ---------------------------------------------------------------------------
# L. Orphan setting — covered by the *runtime* check (see test_meta_audit.py).
#    A static "no consumer" check is a documented GAP (heuristic-prone), so it
#    is exercised at runtime against a real DB row instead.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# O. Backend service without caller — GAP (no static dead-code detector)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason="GAP D-100: the auditor has no static dead-service/caller analysis",
)
def test_gap_backend_service_without_caller(sandbox: Sandbox) -> None:
    sandbox.write(
        "backend/app/services/zz_dead_service.py",
        "class DeadService:\n    def run(self) -> None:\n        return None\n",
    )
    assert any("zz_dead_service" in i for i in sandbox.ids())


# ---------------------------------------------------------------------------
# Q. Channel-aware module drift — GAP (runtime check covers DB rows only)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason="GAP D-100: no static check that a channel-aware module uses channel_id",
)
def test_gap_channel_aware_module_without_channel(sandbox: Sandbox) -> None:
    sandbox.write(
        "backend/app/services/zz_channel_consumer.py",
        "class ChannelConsumer:\n"
        "    def handle(self, payload: dict) -> None:\n"
        "        return None\n",
    )
    assert any("zz_channel_consumer" in i for i in sandbox.ids())


# ---------------------------------------------------------------------------
# N. Unused DB field — GAP (no per-column usage analysis)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason="GAP D-100: no per-column usage analysis",
)
def test_gap_unused_db_field(sandbox: Sandbox) -> None:
    sandbox.patch(
        "backend/app/db/models/setting.py",
        "    value_type: Mapped[str] = mapped_column",
        '    ghost_unused: Mapped[str] = mapped_column(String(8), default="", nullable=False)\n'
        "    value_type: Mapped[str] = mapped_column",
    )
    assert any("ghost_unused" in i for i in sandbox.ids())


# ---------------------------------------------------------------------------
# P. Frontend control without backend behavior — GAP (no wiring check)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason="GAP D-100: no UI-control ↔ endpoint wiring check",
)
def test_gap_control_without_behavior(sandbox: Sandbox) -> None:
    sandbox.append(
        "frontend/src/views/DashboardView.vue",
        '\n<template><button @click="runGhostAction">Запустить</button></template>\n',
    )
    assert any("runGhostAction" in i for i in sandbox.ids())


# ---------------------------------------------------------------------------
# R. Backup destination with no provider (export-only)
# ---------------------------------------------------------------------------
def test_detects_backup_destination_without_provider(sandbox: Sandbox) -> None:
    sandbox.patch(
        "backend/app/db/models/backup_destination.py",
        '    TELEGRAM = "telegram"',
        '    TELEGRAM = "telegram"\n    GHOST_DISK = "ghost_disk"',
    )
    assert "backup.destination_no_module.ghost_disk" in sandbox.errors()


def test_detects_backup_provider_file_missing(sandbox: Sandbox) -> None:
    sandbox.delete("backend/app/services/backup_backends/yandex.py")
    assert "backup.destination_missing.yandex_disk" in sandbox.errors()


# ---------------------------------------------------------------------------
# S. Notification routing gap
# ---------------------------------------------------------------------------
def test_detects_notification_category_without_routing(sandbox: Sandbox) -> None:
    sandbox.patch(
        "backend/app/manager/bus.py",
        'CATEGORY_WORKERS = "workers"',
        'CATEGORY_WORKERS = "workers"\nCATEGORY_GHOST = "ghost"',
    )
    assert "notifications.no_routing.ghost" in sandbox.errors()


# ---------------------------------------------------------------------------
# T. Documentation claim without implementation
# ---------------------------------------------------------------------------
def test_reports_documented_endpoint_that_does_not_exist(sandbox: Sandbox) -> None:
    sandbox.append(
        "docs/API.md",
        "\n## Ghost area\n\nGET /api/v1/ghostarea/list\n",
    )
    hits = [i for i in sandbox.ids() if "docs.api_unknown_prefix" in i]
    assert hits, "documentation-only endpoint produced no finding"
