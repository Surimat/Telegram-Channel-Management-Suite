"""Reaction Manager API tests against the fake provider (no network)."""

from __future__ import annotations

from httpx import AsyncClient


async def _make_profile(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/reactions/profiles",
        json={
            "name": "Тестовый профиль",
            "enabled": True,
            "is_default": True,
            "allowed_emoji": ["❤️", "👍", "🔥"],
            "participation_probability": 1.0,
            "skip_probability": 0.0,
            "delay_min": 1,
            "delay_max": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_categories_listed(bot_client: AsyncClient) -> None:
    resp = await bot_client.get("/api/v1/reactions/categories")
    assert resp.status_code == 200
    keys = {c["key"] for c in resp.json()}
    assert {"donation", "news", "funny", "sad", "angry", "cute", "support",
            "announcement", "neutral"} <= keys


async def test_profile_lifecycle(bot_client: AsyncClient) -> None:
    profile = await _make_profile(bot_client)
    assert profile["is_default"] is True
    assert set(profile["allowed_emoji"]) == {"❤️", "👍", "🔥"}

    listed = await bot_client.get("/api/v1/reactions/profiles")
    assert listed.status_code == 200
    assert any(p["id"] == profile["id"] for p in listed.json())

    updated = await bot_client.patch(
        f"/api/v1/reactions/profiles/{profile['id']}", json={"participation_probability": 0.5}
    )
    assert updated.status_code == 200
    assert updated.json()["participation_probability"] == 0.5

    deleted = await bot_client.delete(f"/api/v1/reactions/profiles/{profile['id']}")
    assert deleted.status_code == 200


async def test_profile_validation_error(bot_client: AsyncClient) -> None:
    profile = await _make_profile(bot_client)
    resp = await bot_client.patch(
        f"/api/v1/reactions/profiles/{profile['id']}",
        json={"participation_probability": 5.0},
    )
    # Pydantic bounds (ge/le) reject it before the service.
    assert resp.status_code == 422


async def test_rules_seeded_and_editable(bot_client: AsyncClient) -> None:
    # Touch an endpoint that triggers default seeding via lifespan-less startup.
    resp = await bot_client.get("/api/v1/system/setup")
    assert resp.status_code == 200
    rules = await bot_client.get("/api/v1/reactions/rules")
    assert rules.status_code == 200

    created = await bot_client.post(
        "/api/v1/reactions/rules",
        json={
            "name": "Своё правило",
            "category": "news",
            "keywords": ["эксклюзив"],
            "allowed_reactions": ["🔥"],
            "priority": 9,
        },
    )
    assert created.status_code == 200, created.text
    rule = created.json()
    assert rule["category"] == "news"

    patched = await bot_client.patch(
        f"/api/v1/reactions/rules/{rule['id']}", json={"enabled": False}
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False


async def test_simulation_donation_plan(bot_client: AsyncClient) -> None:
    await _make_profile(bot_client)
    resp = await bot_client.post(
        "/api/v1/reactions/simulate",
        json={"text": "Спасибо за донат!", "bot_count": 5, "seed": 1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["category"] == "donation"
    assert data["total_bots"] == 5
    assert data["participating"] >= 1
    # Each scheduled step has a human delay and a chosen emoji.
    for step in data["steps"]:
        if step["status"] == "scheduled":
            assert step["emoji"]
            assert step["delay_human"] != "—"


async def test_simulation_deterministic(bot_client: AsyncClient) -> None:
    await _make_profile(bot_client)
    body = {"text": "спасибо за донат", "bot_count": 6, "seed": 42}
    a = (await bot_client.post("/api/v1/reactions/simulate", json=body)).json()
    b = (await bot_client.post("/api/v1/reactions/simulate", json=body)).json()
    # The plan (bot, emoji, delay, status) is reproducible with the same seed;
    # absolute timestamps depend on "now", so they are excluded.
    def strip(steps: list[dict]) -> list[dict]:
        return [{k: v for k, v in s.items() if k != "scheduled_at"} for s in steps]

    assert strip(a["steps"]) == strip(b["steps"])


async def test_ingest_post_and_jobs(bot_client: AsyncClient) -> None:
    # Add a reaction bot via the bots API (fake provider validates the token).
    await bot_client.post(
        "/api/v1/bots",
        json={"token": "123456:ABC", "kind": "ordinary", "title": "Реактор"},
    )
    await _make_profile(bot_client)

    resp = await bot_client.post(
        "/api/v1/reactions/posts",
        json={
            "text": "Спасибо за донат!",
            "channel_id": -100123,
            "telegram_message_id": 321,
            "plan": True,
        },
    )
    assert resp.status_code == 200, resp.text
    post = resp.json()
    assert post["category"] == "donation"

    jobs = await bot_client.get("/api/v1/reactions/jobs")
    assert jobs.status_code == 200
    assert jobs.json()["total"] >= 1


async def test_enable_disable_and_status(bot_client: AsyncClient) -> None:
    enabled = await bot_client.post("/api/v1/reactions/enable")
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    status = await bot_client.get("/api/v1/reactions/status")
    assert status.status_code == 200
    assert "counts" in status.json()

    disabled = await bot_client.post("/api/v1/reactions/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False


async def test_setup_reports_reactions_check(bot_client: AsyncClient) -> None:
    resp = await bot_client.get("/api/v1/system/status")
    assert resp.status_code == 200
    keys = {c["key"] for c in resp.json()["checks"]}
    assert "reactions" in keys
