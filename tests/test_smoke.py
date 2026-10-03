"""Startup smoke tests: the app must build and expose core routes.

This is a lightweight stand-in for the full portable smoke test delivered in
PHASE 10 — it guarantees the application object is constructible and runnable
without external services.
"""

from __future__ import annotations

from backend.app.main import create_app


def test_app_factory_builds() -> None:
    app = create_app()
    assert app.title == "Telegram Channel Management Suite"


def test_expected_routes_present() -> None:
    app = create_app()
    paths = set(app.openapi().get("paths", {}).keys())
    assert "/health" in paths
    assert "/health/deep" in paths
    assert "/api/v1/system/status" in paths
    assert "/api/v1/settings" in paths
    assert "/api/v1/events" in paths
    assert "/api/v1/queue" in paths


async def test_health_and_spa_fallback(client) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200

    # Unknown non-API path falls back to the SPA / info page, not a 404.
    resp = await client.get("/some/spa/route")
    assert resp.status_code == 200
