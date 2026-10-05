"""PHASE 7 service + API tests for the Tiny AI (no model, no network).

Uses the deterministic fake backend so the full pipeline — settings → router →
reaction classification → metrics/events — is exercised for real (no mocks).
"""

from __future__ import annotations

from httpx import AsyncClient

from backend.app.ai.backends import BACKEND_FAKE
from backend.app.db.session import session_scope
from backend.app.services.ai_service import AiService

AI_BASE = "/api/v1/ai"


async def _enable_fake_ai(model_path: str = "/tmp/fake.gguf") -> None:
    """Turn AI on with the deterministic fake backend via DB settings."""
    async with session_scope() as session:
        service = AiService(session)
        await service.set_setting("ai_enabled", True)
        await service.set_setting("ai_backend", BACKEND_FAKE)
        await service.set_setting("ai_model_path", model_path)
        await session.commit()


async def test_ai_status_disabled_by_default(client: AsyncClient) -> None:
    resp = await client.get(f"{AI_BASE}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["effective"] is False
    # Friendly, non-technical wording.
    assert "правил" in body["reason"] or "AI выключен" in body["reason"]


async def test_ai_settings_carry_plain_language_help(client: AsyncClient) -> None:
    resp = await client.get(f"{AI_BASE}/settings")
    assert resp.status_code == 200
    items = {i["key"]: i for i in resp.json()["items"]}
    assert "ai_enabled" in items
    entry = items["ai_timeout_seconds"]
    assert entry["what_it_does"]
    assert entry["why"]
    assert entry["safe_default"]


async def test_ai_settings_reject_bad_value(client: AsyncClient) -> None:
    resp = await client.put(f"{AI_BASE}/settings", json={"values": {"ai_timeout_seconds": 9999}})
    assert resp.status_code == 400
    resp2 = await client.put(
        f"{AI_BASE}/settings", json={"values": {"ai_model_path": "model.bin"}}
    )
    assert resp2.status_code == 400


async def test_ai_settings_update_and_toggle(client: AsyncClient) -> None:
    resp = await client.put(
        f"{AI_BASE}/settings",
        json={"values": {"ai_enabled": True, "ai_backend": BACKEND_FAKE}},
    )
    assert resp.status_code == 200
    items = {i["key"]: i for i in resp.json()["items"]}
    assert items["ai_enabled"]["value"] == "true"


async def test_ai_classify_rules_fast_path(client: AsyncClient) -> None:
    await _enable_fake_ai()
    resp = await client.post(f"{AI_BASE}/classify", json={"text": "Спасибо за донат, друзья!"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "donation"
    assert body["source"] == "rules"
    assert body["ai_used"] is False


async def test_ai_classify_encoder_mode(client: AsyncClient) -> None:
    """The lightweight encoder works with AI disabled (no model, weak-PC path)."""
    resp = await client.post(
        f"{AI_BASE}/classify",
        json={"text": "это очень смешно, ахаха", "mode": "encoder"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "funny"
    assert body["encoder_attempted"] is True
    assert body["encoder_used"] is True
    assert body["ai_used"] is False
    assert body["intent"]


async def test_ai_classify_encoder_mode_never_requires_a_model(client: AsyncClient) -> None:
    # Even with AI explicitly off, encoder mode returns a real answer or a clean
    # fallback — it never raises and never demands a model download.
    resp = await client.post(
        f"{AI_BASE}/classify",
        json={"text": "совершенно непонятный текст без категории", "mode": "encoder"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["encoder_attempted"] is True
    assert body["fallback_used"] is True


async def test_ai_classify_uses_fake_when_rules_unsure(client: AsyncClient) -> None:
    await _enable_fake_ai()
    # No rule keywords, but the fake backend's data-block keyword match applies.
    resp = await client.post(f"{AI_BASE}/classify", json={"text": "привет всем, приятной новости"})
    assert resp.status_code == 200
    # Rules see "новости" → confident enough → rules win without the AI.
    assert resp.json()["source"] == "rules"
    # Force AI mode instead to exercise the AI path.
    forced = await client.post(
        f"{AI_BASE}/classify", json={"text": "совершенно непонятная фраза", "mode": "ai"}
    )
    assert forced.status_code == 200
    assert forced.json()["ai_attempted"] is True


async def test_ai_classify_ai_mode_falls_back_without_model(client: AsyncClient) -> None:
    # AI disabled and no model → AI-only mode must still return a safe result.
    resp = await client.post(
        f"{AI_BASE}/classify", json={"text": "Спасибо за донат!", "mode": "ai"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fallback_used"] is True
    assert body["source"] in ("fallback", "rules", "llm")


async def test_ai_model_check_without_runtime(client: AsyncClient, monkeypatch) -> None:
    await _enable_fake_ai()
    # Force the runtime to look unavailable for this check.
    from backend.app.services import ai_service as mod

    async def _no_backend(self):
        from backend.app.ai.backends import FakeLlmBackend

        b = FakeLlmBackend(available=False)
        return b

    monkeypatch.setattr(mod.AiService, "_backend", _no_backend)
    resp = await client.post(f"{AI_BASE}/model/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["runtime_available"] is False
    assert body["message"]


async def test_ai_model_check_missing_file(client: AsyncClient) -> None:
    await _enable_fake_ai(model_path="/tmp/definitely-missing-model.gguf")
    resp = await client.post(f"{AI_BASE}/model/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["model_exists"] is False


async def test_ai_model_check_success_with_fake(tmp_path, client: AsyncClient) -> None:
    model = tmp_path / "tiny.gguf"
    model.write_bytes(b"\x00" * 16)
    await _enable_fake_ai(model_path=str(model))
    resp = await client.post(f"{AI_BASE}/model/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["model_exists"] is True
    assert body["size_bytes"] == 16


async def test_ai_metrics_after_classify(client: AsyncClient) -> None:
    await _enable_fake_ai()
    await client.post(f"{AI_BASE}/classify", json={"text": "Спасибо за донат!"})
    resp = await client.get(f"{AI_BASE}/metrics")
    assert resp.status_code == 200
    assert resp.json()["total_classifications"] >= 1


async def test_ai_history_records(client: AsyncClient) -> None:
    await _enable_fake_ai()
    await client.post(f"{AI_BASE}/classify", json={"text": "Спасибо за донат!"})
    resp = await client.get(f"{AI_BASE}/history")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


async def test_ai_overview_shape(client: AsyncClient) -> None:
    resp = await client.get(f"{AI_BASE}/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"status", "metrics", "today"}
    assert "reason" in body["status"]


async def test_ai_models_listing_empty(client: AsyncClient) -> None:
    resp = await client.get(f"{AI_BASE}/models")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_reaction_simulation_reports_ai_fields(bot_client: AsyncClient) -> None:
    await _enable_fake_ai()
    resp = await bot_client.post(
        "/api/v1/reactions/simulate",
        json={"text": "Спасибо за донат, друзья!", "bot_count": 3, "seed": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert {"tone", "mode", "ai_attempted", "ai_used", "fallback_used"} <= set(body)
    assert body["source"] == "rules"


async def test_reaction_simulation_ai_mode(bot_client: AsyncClient) -> None:
    await _enable_fake_ai()
    resp = await bot_client.post(
        "/api/v1/reactions/simulate",
        json={"text": "что-то непонятное", "bot_count": 3, "mode": "ai"},
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "ai"


async def test_setup_wizard_reports_ai_check(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/system/status")
    assert resp.status_code == 200
    keys = {c["key"] for c in resp.json()["checks"]}
    assert "ai" in keys
