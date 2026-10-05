"""Help / novice-mode tests.

The explanations must be available to every client, cover the required concepts,
and the "show explanations" preference must default to ON and be persisted.
"""

from __future__ import annotations

from httpx import AsyncClient

from backend.app.services.help_topics import all_topics, topic

REQUIRED_KEYS = {
    "manager_bot",
    "managed_bot",
    "telegram_account",
    "session",
    "channel",
    "source",
    "audience",
    "invite",
    "reaction_profile",
    "rules",
    "tiny_ai",
    "miniapp",
    "permission_probe",
    "proxy",
    "backup",
    "migration",
    "scheduler",
    "queue",
    "update",
    "provisioning",
    "content_studio",
    "content_source",
    "content_rights",
    "bot_factory",
    "lan_mesh",
}


def test_catalog_covers_required_concepts() -> None:
    keys = {t["key"] for t in all_topics()}
    assert keys >= REQUIRED_KEYS


def test_every_topic_answers_the_beginner_questions() -> None:
    for item in all_topics():
        assert item["title"].strip(), item["key"]
        assert item["what"].strip(), item["key"]
        assert item["why"].strip(), item["key"]
        assert item["when_off"].strip(), item["key"]
        assert item["safe_default"].strip(), item["key"]


def test_manager_bot_text_matches_brief() -> None:
    t = topic("manager_bot")
    assert t is not None
    assert "не является вашим каналом" in t.safe_default
    assert "уведомления" in t.what


async def test_help_topics_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/help/topics")
    assert resp.status_code == 200
    items = resp.json()
    assert {i["key"] for i in items} >= REQUIRED_KEYS
    # No secret-bearing fields ever appear in the catalog.
    blob = str(items).lower()
    for forbidden in ("api_hash", "token", "password", "session_string"):
        assert forbidden not in blob


async def test_prefs_default_on_and_persist(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/help/prefs")
    assert resp.status_code == 200
    assert resp.json()["show_explanations"] is True

    resp = await client.put("/api/v1/help/prefs", json={"show_explanations": False})
    assert resp.status_code == 200
    assert resp.json()["show_explanations"] is False

    # Persisted across requests.
    resp = await client.get("/api/v1/help/prefs")
    assert resp.json()["show_explanations"] is False
