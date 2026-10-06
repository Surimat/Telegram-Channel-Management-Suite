"""Architecture consistency tests (v1.5).

These run the *static* half of the Consistency Auditor in CI, so cross-module
drift fails a pull request instead of reaching the owner:

* every ORM table has a migration;
* every API route the frontend calls exists;
* every scheduler job kind has a handler;
* every frontend route points at a real view;
* providers come in real + fake pairs;
* i18n keys are complete;
* the help catalog covers what the UI references;
* documented API prefixes are real.

Hard drift is asserted as an error; heuristic noise (unused routers, orphan help
topics) is allowed and only reported by the runtime panel.
"""

from __future__ import annotations

from backend.app.services.consistency_checks import (
    check_api_route_frontend_client,
    check_capability_implementation,
    check_capability_registry,
    check_documented_endpoints,
    check_frontend_route_view,
    check_help_catalog_usage,
    check_i18n_completeness,
    check_model_migration,
    check_provider_registry,
    check_scheduler_job_handlers,
)
from backend.app.services.consistency_types import SEVERITY_ERROR


def _errors(findings):  # type: ignore[no-untyped-def]
    return [f for f in findings if f.severity == SEVERITY_ERROR]


def test_every_model_has_a_migration() -> None:
    assert _errors(check_model_migration()) == []


def test_frontend_api_calls_exist() -> None:
    assert _errors(check_api_route_frontend_client()) == []


def test_every_job_kind_has_a_handler() -> None:
    assert _errors(check_scheduler_job_handlers()) == []


def test_frontend_routes_point_at_real_views() -> None:
    assert _errors(check_frontend_route_view()) == []


def test_providers_have_real_and_fake_implementations() -> None:
    assert _errors(check_provider_registry()) == []


def test_capability_requirements_are_known() -> None:
    assert _errors(check_capability_registry()) == []


def test_capabilities_have_implementations() -> None:
    # A registry entry must not claim `implemented` without real code.
    assert _errors(check_capability_implementation()) == []


def test_auditor_never_swallows_a_failed_check() -> None:
    # Every registered check must surface as a finding, not vanish. Run the full
    # static suite and require the two audit-only checks to be present (i.e. the
    # runner did not silently drop them).
    from backend.app.services.consistency_checks import run_static_checks

    ids = {f.id for f in run_static_checks()}
    assert not any(i.startswith("audit.check_failed.") for i in ids)


def test_i18n_keys_are_complete() -> None:
    assert _errors(check_i18n_completeness()) == []


def test_ui_help_topics_exist_in_catalog() -> None:
    assert _errors(check_help_catalog_usage()) == []


def test_documented_api_prefixes_are_known() -> None:
    # Warning-level drift is allowed; only errors would fail here.
    assert _errors(check_documented_endpoints()) == []


def test_missing_source_tree_is_info_not_error(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # The runtime Docker image has no frontend/docs source. A source-comparison
    # check must report "unavailable" (info), never raise into an error, and the
    # backend-only checks must still run (D-096).
    from backend.app.services import consistency_checks as cc

    monkeypatch.setattr(cc, "FRONTEND", tmp_path / "frontend-absent")
    monkeypatch.setattr(cc, "DOCS", tmp_path / "docs-absent")
    findings = cc.run_static_checks()
    ids = {f.id for f in findings}
    assert not any(i.startswith("audit.check_failed.") for i in ids)
    assert "audit.source_unavailable.check_api_route_frontend_client" in ids
    assert "audit.source_unavailable.check_documented_endpoints" in ids
    unavailable = [f for f in findings if f.id.startswith("audit.source_unavailable.")]
    assert all(f.severity == "info" for f in unavailable)
