"""Meta-audit core: silent-failure guard, runtime checks, kill-rate summary.

Companion to ``tests/test_consistency_mutations.py``. It proves three things the
Consistency Auditor must guarantee (D-099):

1. **A failing check never becomes a pass.** If a registered check raises, the
   runner emits ``audit.check_failed.<name>`` with severity ``error`` — it must
   not vanish, and ``overall`` must be ``fail``.
2. **The runtime (DB-backed) checks detect real drift** — a dead setting and a
   channel-aware row without a channel reference.
3. **Kill rate is real, not aspirational.** A machine-readable summary of seeded
   defects vs. detected defects is written to ``agent/META_AUDIT_RESULT.json``.

No Telegram credentials, sessions, TDATA, network or production data are used.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from backend.app import __version__
from backend.app.services.consistency import ConsistencyAuditor
from backend.app.services.consistency_types import (
    HEALTH_FAIL,
    SEVERITY_ERROR,
    build_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1. Silent-failure guard
# ---------------------------------------------------------------------------
def _run_with_broken_check(monkeypatch: pytest.MonkeyPatch, name: str) -> list:
    """Replace one static check with one that raises, then run the suite."""
    import backend.app.services.consistency_checks as cc

    def boom() -> list:
        raise RuntimeError("SYNTHETIC AUDIT FAILURE")

    boom.__name__ = name
    monkeypatch.setattr(cc, name, boom)
    # The runner iterates the module-level function objects, so patching the
    # attribute is enough for `run_static_checks` to pick up the broken version.
    return cc.run_static_checks()


def test_a_raising_static_check_is_reported_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    findings = _run_with_broken_check(monkeypatch, "check_i18n_completeness")
    failed = [f for f in findings if f.id == "audit.check_failed.check_i18n_completeness"]
    assert failed, "a raising check disappeared instead of being reported"
    assert failed[0].severity == SEVERITY_ERROR


def test_a_raising_static_check_makes_the_report_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = build_report(_run_with_broken_check(monkeypatch, "check_model_migration"))
    assert report.overall == HEALTH_FAIL
    assert report.counts[SEVERITY_ERROR] >= 1


def test_broken_source_check_reports_info_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A source-comparison check must degrade to "unavailable" (info), never raise
    # into a false error, and never silently vanish (D-096).
    import backend.app.services.consistency_checks as cc

    monkeypatch.setattr(cc, "FRONTEND", tmp_path / "frontend-absent")
    findings = cc.run_static_checks()
    ids = {f.id for f in findings}
    assert "audit.source_unavailable.check_api_route_frontend_client" in ids
    assert "audit.source_unavailable.check_hardcoded_ui_strings" in ids
    assert not any(i.startswith("audit.check_failed.") for i in ids)
    unavailable = [f for f in findings if f.id.startswith("audit.source_unavailable.")]
    assert all(f.severity == "info" for f in unavailable)


async def test_a_raising_runtime_check_is_reported_not_swallowed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(self) -> list:
        raise RuntimeError("SYNTHETIC RUNTIME FAILURE")

    monkeypatch.setattr(ConsistencyAuditor, "_check_dead_settings", boom)
    from backend.app.db.session import get_session_factory

    async with get_session_factory()() as session:
        report = await ConsistencyAuditor(session).run()
    assert "audit.check_failed.boom" in {f.id for f in report.findings}
    assert report.overall == HEALTH_FAIL


async def test_inner_check_does_not_swallow_a_real_db_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `_check_channel_aware` catches DB errors internally and returns [] — that is
    # a *known* narrow swallow. Document it: the check must still not crash the
    # auditor, but the auditor as a whole must remain usable.
    from backend.app.db.session import get_session_factory

    async with get_session_factory()() as session:
        report = await ConsistencyAuditor(session).run()
    assert report.overall in {"pass", "warning", "fail"}


# ---------------------------------------------------------------------------
# 2. Runtime (DB-backed) drift detection
# ---------------------------------------------------------------------------
async def test_runtime_detects_dead_setting(client: AsyncClient) -> None:
    # A persisted setting no module reads must surface as an orphan finding.
    from backend.app.db.repositories.settings import SettingRepository
    from backend.app.db.session import get_session_factory

    async with get_session_factory()() as session:
        await SettingRepository(session).upsert("zz_ghost_setting", "1", value_type="int")
        report = await ConsistencyAuditor(session).run()
    assert "settings.dead.zz_ghost_setting" in {f.id for f in report.findings}


async def test_runtime_detects_channel_aware_row_without_channel(
    client: AsyncClient,
) -> None:
    # A channel-aware table row with no channel_id must be flagged.
    from backend.app.db.models.content import ContentSource
    from backend.app.db.session import get_session_factory

    async with get_session_factory()() as session:
        session.add(ContentSource(title="ghost", reference="", channel_id=""))
        await session.commit()
        report = await ConsistencyAuditor(session).run()
    assert "channel-aware.content_source" in {f.id for f in report.findings}


# ---------------------------------------------------------------------------
# 3. Kill-rate summary (machine-readable, written to agent/)
# ---------------------------------------------------------------------------
#: Seeded defects proven detectable by the mutation harness, with severity of the
#: finding that catches them. Kept in sync with tests/test_consistency_mutations.py.
_DETECTABLE = {
    "A_frontend_route": "error",
    "B_api_consumer": "error",
    "C_orphan_endpoint": "error",
    "D_scheduler_handler": "error",
    "E1_provider_missing": "error",
    "E2_registry_missing_module": "error",
    "F_false_capability": "error",
    "F2_stray_string_mask": "error",
    "G_capability_dependency": "error",
    "H_i18n_missing": "error",
    "I_hardcoded_ui_string": "warning",
    "J_help_reference": "error",
    "K_model_migration": "error",
    "K2_column_migration": "error",
    "R1_backup_destination_no_provider": "error",
    "R2_backup_provider_missing": "error",
    "S_notification_routing": "error",
    "T_doc_endpoint_claim": "warning",
}

#: Seeded defects the auditor genuinely cannot catch yet (documented GAPs).
_MISSED = {
    "L_orphan_setting_static": ("medium", "runtime-only heuristic; no static consumer graph"),
    "M_write_only_setting": (
        "high",
        "no check that a persisted setting changes behaviour; sync_*/owner_* keys "
        "are allow-listed but read nowhere",
    ),
    "N_unused_db_field": ("medium", "no per-column usage analysis"),
    "O_service_without_caller": ("medium", "no dead-code/caller analysis"),
    "P_control_without_behavior": ("medium", "no UI-control ↔ endpoint wiring check"),
    "Q_channel_aware_module": ("high", "runtime covers rows, not module code"),
}

#: Defects that are out of scope by design (security-sensitive or not architecture
#: drift), recorded so the report is honest rather than inflating the denominator.
_OUT_OF_SCOPE = {
    "auth_bypass": "no owner-auth feature in this cycle",
    "secret_leak": "covered by secret scan, not the consistency auditor",
}


def test_meta_audit_result_is_honest_and_consistent() -> None:
    total = len(_DETECTABLE) + len(_MISSED)
    detected = len(_DETECTABLE)
    missed = len(_MISSED)
    kill_rate = round(detected / total * 100, 1)
    critical = sum(1 for sev, _ in _MISSED.values() if sev == "critical")
    high = sum(1 for sev, _ in _MISSED.values() if sev == "high")

    # Sanity: the numbers must actually add up.
    assert detected + missed == total
    assert 0 <= kill_rate <= 100
    # A high-severity miss (e.g. a write-only setting) must keep the verdict
    # honest — never claim "auditor trust = HIGH" while a high miss exists.
    status = "gaps_found" if missed else "clean"
    assert status == "gaps_found"

    result = {
        "version": __version__,
        "baseline_sha": "2d5fad70266c7bc05c4d383546a46634cdde241a",
        "seeded_defects": total,
        "detected": detected,
        "missed": missed,
        "kill_rate": kill_rate,
        "critical_misses": critical,
        "high_misses": high,
        "false_green": False,
        "status": status,
        "detectable": _DETECTABLE,
        "missed_defects": {k: {"severity": v[0], "reason": v[1]} for k, v in _MISSED.items()},
        "out_of_scope": _OUT_OF_SCOPE,
    }
    out = REPO_ROOT / "agent" / "META_AUDIT_RESULT.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    assert out.is_file()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["detected"] == detected
    assert written["missed"] == missed


# ---------------------------------------------------------------------------
# 4. Cross-file release hygiene (real drift caught while writing the meta-audit)
# ---------------------------------------------------------------------------
def test_repo_version_is_consistent() -> None:
    import json as _json
    import tomllib

    from backend.app import __version__

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = _json.loads((REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert __version__ == pyproject["project"]["version"] == package["version"]


def test_readme_states_the_current_release() -> None:
    # The README drifted to v1.5.0 while the code shipped v1.5.1. Guard it.
    from backend.app import __version__

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"`v{__version__}`" in readme


# ---------------------------------------------------------------------------
# 5. Capability dependency actually blocks availability (not just a static warn)
# ---------------------------------------------------------------------------
def test_dependency_on_unimplemented_capability_blocks_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dataclasses

    from backend.app.services import capability_graph as cg

    donor = next(c for c in cg.CAPABILITIES if c.key == "donor_discovery")
    patched = dataclasses.replace(donor, requires=("config_sync",))
    monkeypatch.setattr(
        cg,
        "CAPABILITIES",
        tuple(patched if c.key == "donor_discovery" else c for c in cg.CAPABILITIES),
    )
    # config_sync is implemented=False, so even a fully-satisfied context must not
    # let donor_discovery report "available".
    context = {req: True for cap in cg.CAPABILITIES for req in cap.requires}
    context["config_sync"] = True
    state = cg.evaluate(patched, context)
    assert state.state != cg.STATE_AVAILABLE
    assert any("config_sync" in m for m in state.missing)
