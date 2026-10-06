"""Consistency Auditor tests (v1.5).

Covers the report model, the runtime DB-backed checks (via the fake-free test
database) and the API surface. Static checks are covered by
``test_architecture_consistency.py``.
"""

from __future__ import annotations

from httpx import AsyncClient

from backend.app.services.consistency import ConsistencyAuditor, run_static_checks
from backend.app.services.consistency_types import (
    HEALTH_FAIL,
    HEALTH_PASS,
    HEALTH_WARNING,
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    Finding,
    build_report,
)


def test_build_report_marks_fail_on_error() -> None:
    findings = [
        Finding(
            id="x",
            category="database",
            severity=SEVERITY_ERROR,
            confidence="high",
            title="t",
            detail="d",
        )
    ]
    report = build_report(findings)
    assert report.overall == HEALTH_FAIL
    assert report.counts[SEVERITY_ERROR] == 1


def test_build_report_marks_warning() -> None:
    report = build_report(
        [
            Finding(
                id="x",
                category="api",
                severity=SEVERITY_WARNING,
                confidence="medium",
                title="t",
                detail="d",
            )
        ]
    )
    assert report.overall == HEALTH_WARNING


def test_build_report_is_pass_when_only_info() -> None:
    report = build_report(
        [
            Finding(
                id="x",
                category="settings",
                severity=SEVERITY_INFO,
                confidence="low",
                title="t",
                detail="d",
            )
        ]
    )
    assert report.overall == HEALTH_PASS


def test_finding_maps_to_area() -> None:
    f = Finding(
        id="x",
        category="database",
        severity=SEVERITY_INFO,
        confidence="low",
        title="t",
        detail="d",
    )
    assert f.area == "configuration"


def test_static_checks_are_deterministic_and_have_no_errors() -> None:
    first = run_static_checks()
    second = run_static_checks()
    assert {f.id for f in first} == {f.id for f in second}
    assert [f for f in first if f.severity == SEVERITY_ERROR] == []


async def test_runtime_auditor_runs_on_empty_db(client: AsyncClient) -> None:
    # The `client` fixture creates the schema; run the auditor directly.
    from backend.app.db.session import get_session_factory

    async with get_session_factory()() as session:
        report = await ConsistencyAuditor(session).run()
    assert report.overall in {HEALTH_PASS, HEALTH_WARNING, HEALTH_FAIL}
    assert {a.key for a in report.areas} == {
        "configuration",
        "integration",
        "security",
        "documentation",
        "ux",
    }


async def test_consistency_api(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/consistency")
    assert resp.status_code == 200
    data = resp.json()
    assert "overall" in data
    assert isinstance(data["findings"], list)
    assert isinstance(data["areas"], list)
    # No secret-looking content is ever returned.
    blob = resp.text.lower()
    assert "api_hash" not in blob
    assert "session_string" not in blob


async def test_capability_graph_api(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/capability-graph")
    assert resp.status_code == 200
    items = resp.json()
    keys = {i["key"] for i in items}
    assert {"reaction", "bot_only_analytics", "ai_ru", "donor_discovery"} <= keys
    for item in items:
        assert item["state"] in {
            "available",
            "partial",
            "needs_setup",
            "unavailable",
            "not_implemented",
        }
        assert item["state_label"]


async def test_unimplemented_capabilities_are_never_available(client: AsyncClient) -> None:
    """A registry entry without a real feature must not report `available`."""
    resp = await client.get("/api/v1/capability-graph")
    items = {i["key"]: i for i in resp.json()}
    # ``media_conversion`` has no implementation and no service anchor, so it must
    # never report available. ``config_sync`` is now implemented (v1.6) but still
    # must not be reported available until its requirements are satisfied.
    for key in ("media_conversion",):
        assert items[key]["state"] == "not_implemented", key
        assert items[key]["implemented"] is False, key
        assert items[key]["state"] != "available", key
    assert items["config_sync"]["implemented"] is True, "config_sync"
    assert items["config_sync"]["state"] != "available", "config_sync"


async def test_capability_graph_language_follows_ui_preference(client: AsyncClient) -> None:
    """The saved language preference must localise capability labels."""
    await client.put("/api/v1/help/prefs", json={"language": "en"})
    items = {i["key"]: i for i in (await client.get("/api/v1/capability-graph")).json()}
    assert items["donor_discovery"]["title"] == "Donor discovery"
    # config_sync is implemented but unconfigured on a fresh install.
    assert items["config_sync"]["state_label"] == "Unavailable"
    assert items["media_conversion"]["state_label"] == "Not implemented"

    # An explicit query parameter still wins over the preference.
    items = {
        i["key"]: i
        for i in (
            await client.get("/api/v1/capability-graph", params={"language": "ru"})
        ).json()
    }
    assert items["donor_discovery"]["title"] == "Поиск источников"

    await client.put("/api/v1/help/prefs", json={"language": "ru"})


async def test_capability_graph_reports_missing_setup_on_empty_db(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/capability-graph")
    items = {i["key"]: i for i in resp.json()}
    # Nothing is configured, so reactions cannot be available yet.
    assert items["reaction"]["state"] != "available"
    assert items["reaction"]["missing"]
    assert items["reaction"]["missing_fixes"]
