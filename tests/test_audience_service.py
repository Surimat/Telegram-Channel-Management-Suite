"""AudienceService tests: scanning, dedup, tags, export/import, recovery.

Everything runs against the pure :class:`FakeAudienceProvider` / fake session
provider — no Telegram credentials and no network (decision D-001).
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from backend.app.db.models.audience import (
    AudienceUser,
    Completeness,
    ScanStatus,
    SourceType,
)
from backend.app.db.models.session import SessionStatus, UserSession
from backend.app.providers.fake_audience import FakeAudienceProvider, fake_audience_provider
from backend.app.providers.fake_session import (
    FakeAudienceScenario,
    make_fake_users,
)
from backend.app.services.audience_service import AudienceService, AudienceServiceError


@pytest_asyncio.fixture
async def svc():
    """An AudienceService bound to a temp DB with one online fake account."""
    from backend.app.db.session import dispose_engine, init_models, session_scope

    await init_models()
    async with session_scope() as session:
        session.add(
            UserSession(
                telegram_user_id=1000001,
                username="fake_user",
                display_name="Fake User",
                status=SessionStatus.ONLINE,
                enabled=True,
                api_id="1",
            )
        )
        await session.flush()
        yield session
    await dispose_engine()


def _service(session, provider: FakeAudienceProvider | None = None) -> AudienceService:
    return AudienceService(session, audience_provider=provider)


async def _drain(service: AudienceService, source_id: str, *, chunk: int = 100) -> None:
    """Run the scan loop until the source finishes (mirrors the scheduler)."""
    for _ in range(1000):
        await service.run_scan_chunk()
        source = await service.get_source(source_id)
        if source.scan_status in {
            ScanStatus.COMPLETED,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED,
            ScanStatus.PAUSED,
        }:
            return
    raise AssertionError("scan did not finish")


async def test_add_and_parse_reference(svc) -> None:
    service = _service(svc)
    s = await service.add_source(reference="https://t.me/durov")
    assert s.username == "durov"
    assert s.telegram_id is None

    s2 = await service.add_source(reference="@news", source_type=SourceType.CHANNEL)
    assert s2.username == "news"

    s3 = await service.add_source(reference="123456")
    assert s3.telegram_id == 123456


async def test_add_source_requires_reference(svc) -> None:
    service = _service(svc)
    with pytest.raises(AudienceServiceError):
        await service.add_source(reference="   ")


async def test_scan_imports_users_without_duplicates(svc) -> None:
    provider = fake_audience_provider(count=120)
    service = _service(svc, provider)
    source = await service.add_source(reference="@source")

    await service.start_scan(source.id)
    await _drain(service, source.id)

    refreshed = await service.get_source(source.id)
    assert refreshed.scan_status == ScanStatus.COMPLETED
    assert refreshed.completeness == Completeness.COMPLETE
    assert refreshed.discovered_count == 120
    assert refreshed.new_count == 120
    assert refreshed.duplicate_count == 0
    _, total = await service.list_users()
    assert total == 120
    assert provider.page_calls  # pages were actually requested in chunks


async def test_repeated_scan_dedups(svc) -> None:
    provider = fake_audience_provider(count=30)
    service = _service(svc, provider)
    source = await service.add_source(reference="@source")

    await service.start_scan(source.id)
    await _drain(service, source.id)
    first = await service.get_source(source.id)
    assert first.new_count == 30

    # Second scan: same people must not create new rows.
    await service.start_scan(source.id)
    await _drain(service, source.id)
    second = await service.get_source(source.id)
    assert second.new_count == 0
    assert second.duplicate_count == 30
    _, total = await service.list_users()
    assert total == 30


async def test_user_in_multiple_sources(svc) -> None:
    provider = fake_audience_provider(count=10)
    service = _service(svc, provider)
    s1 = await service.add_source(reference="@one")
    s2 = await service.add_source(reference="@two")

    await service.start_scan(s1.id)
    await _drain(service, s1.id)
    await service.start_scan(s2.id)
    await _drain(service, s2.id)

    _, total = await service.list_users()
    assert total == 10  # deduplicated across sources

    user = (await service.list_users())[0][0]
    sources = await service.sources_of_user(user.id)
    assert len(sources) == 2


async def test_partial_result_is_reported(svc) -> None:
    # Telegram reports 500 but only exposes 25 members.
    scenario = FakeAudienceScenario(participants=make_fake_users(25), reported_total=500)
    provider = FakeAudienceProvider(scenario)
    service = _service(svc, provider)
    source = await service.add_source(reference="@big")

    await service.start_scan(source.id)
    await _drain(service, source.id)

    refreshed = await service.get_source(source.id)
    assert refreshed.completeness == Completeness.PARTIAL
    assert refreshed.discovered_count == 25
    assert "частичн" in service.explain_scan_result(refreshed).lower()


async def test_no_access_when_participants_hidden(svc) -> None:
    scenario = FakeAudienceScenario(participants=[], participants_hidden=True, reported_total=999)
    provider = FakeAudienceProvider(scenario)
    service = _service(svc, provider)
    source = await service.add_source(reference="@private")

    await service.start_scan(source.id)
    await _drain(service, source.id)

    refreshed = await service.get_source(source.id)
    assert refreshed.completeness == Completeness.NO_ACCESS
    assert refreshed.scan_status == ScanStatus.FAILED


async def test_flood_wait_pauses_scan(svc) -> None:
    from backend.app.providers.errors import FloodWaitError

    scenario = FakeAudienceScenario(
        participants=make_fake_users(10), participants_error=FloodWaitError(60)
    )
    provider = FakeAudienceProvider(scenario)
    service = _service(svc, provider)
    source = await service.add_source(reference="@x")
    await service.start_scan(source.id)
    await _drain(service, source.id)

    refreshed = await service.get_source(source.id)
    # FloodWait must pause the scan (never bypassed, D-006).
    assert refreshed.scan_status == ScanStatus.PAUSED
    assert "подождать" in refreshed.last_error.lower() or refreshed.last_error


async def test_pause_resume_cancel(svc) -> None:
    provider = fake_audience_provider(count=200)
    service = _service(svc, provider)
    source = await service.add_source(reference="@x")

    await service.start_scan(source.id)
    await service.pause_scan(source.id)
    paused = await service.get_source(source.id)
    assert paused.scan_status == ScanStatus.PAUSED

    await service.resume_scan(source.id)
    resumed = await service.get_source(source.id)
    assert resumed.scan_status == ScanStatus.SCANNING

    await service.cancel_scan(source.id)
    cancelled = await service.get_source(source.id)
    assert cancelled.scan_status == ScanStatus.CANCELLED


async def test_progress_persists_offset(svc) -> None:
    provider = fake_audience_provider(count=120, page_size=50)
    service = _service(svc, provider)
    source = await service.add_source(reference="@x")
    await service.start_scan(source.id)

    # Process exactly one batch and check the persisted offset.
    outcome = await service.process_scan_batch(source.id, batch_size=50)
    assert outcome.fetched == 50
    refreshed = await service.get_source(source.id)
    assert refreshed.scanned_offset == 50


async def test_recover_pauses_scanning_sources(svc) -> None:
    provider = fake_audience_provider(count=50)
    service = _service(svc, provider)
    source = await service.add_source(reference="@x")
    await service.start_scan(source.id)
    assert (await service.get_source(source.id)).scan_status == ScanStatus.SCANNING

    paused = await service.recover()
    assert paused == 1
    refreshed = await service.get_source(source.id)
    assert refreshed.scan_status == ScanStatus.PAUSED
    assert refreshed.scanned_offset == 0


async def test_tags_lifecycle(svc) -> None:
    provider = fake_audience_provider(count=5)
    service = _service(svc, provider)
    source = await service.add_source(reference="@x")
    await service.start_scan(source.id)
    await _drain(service, source.id)

    users, _ = await service.list_users()
    ids = [u.id for u in users[:3]]

    assert await service.add_tags(ids, ["vip", "review"]) == 3
    tags = {t["name"]: t["count"] for t in await service.list_tags()}
    assert tags["vip"] == 3

    assert await service.rename_tag("vip", "important") == 3
    tags = {t["name"]: t["count"] for t in await service.list_tags()}
    assert "important" in tags and "vip" not in tags

    assert await service.remove_tags(ids[:1], ["review"]) == 1
    assert await service.delete_tag("important") == 3


async def test_export_csv_and_json(svc, tmp_path) -> None:
    provider = fake_audience_provider(count=8)
    service = _service(svc, provider)
    source = await service.add_source(reference="@x")
    await service.start_scan(source.id)
    await _drain(service, source.id)

    csv_result = await service.export_audience(fmt="csv")
    assert csv_result.row_count == 8
    assert csv_result.path.endswith(".csv")
    assert "telegram_user_id" in csv_result.fields
    from pathlib import Path

    content = Path(csv_result.path).read_text(encoding="utf-8")
    assert "telegram_user_id" in content.splitlines()[0]

    json_result = await service.export_audience(fmt="json")
    data = json.loads(Path(json_result.path).read_text(encoding="utf-8"))
    assert len(data) == 8


async def test_export_pii_requires_setting(svc) -> None:
    service = _service(svc, fake_audience_provider(count=1))
    with pytest.raises(AudienceServiceError):
        await service.export_audience(fmt="csv", include_pii=True)


async def test_import_csv_and_dedup(svc) -> None:
    service = _service(svc)
    csv_data = (
        "telegram_user_id,username,first_name\n"
        "1,alpha,Ann\n"
        "2,beta,Bob\n"
        "2,beta-dup,Bob\n"
        "notanumber,bad,Bad\n"
    )
    result = await service.import_audience(data=csv_data, fmt="csv")
    assert result["created"] == 2
    assert result["invalid"] == 2  # duplicate id + invalid id

    # Re-import merges rather than duplicating.
    result2 = await service.import_audience(data=csv_data, fmt="csv")
    assert result2["created"] == 0
    assert result2["merged"] == 2
    _, total = await service.list_users()
    assert total == 2


async def test_import_json(svc) -> None:
    service = _service(svc)
    payload = json.dumps(
        [
            {"telegram_user_id": 10, "username": "ten"},
            {"telegram_user_id": 11, "username": "eleven"},
        ]
    )
    result = await service.import_audience(data=payload, fmt="json")
    assert result["created"] == 2


async def test_dashboard_and_statistics(svc) -> None:
    provider = fake_audience_provider(count=40)
    service = _service(svc, provider)
    source = await service.add_source(reference="@x")
    await service.start_scan(source.id)
    await _drain(service, source.id)

    dash = await service.dashboard()
    assert dash["sources_total"] == 1
    assert dash["unique_users"] == 40
    assert dash["total_records"] == 40
    assert dash["by_completeness"]["complete"] == 1

    stats = await service.source_statistics(source.id)
    assert stats["linked_users"] == 40


async def test_score_is_explainable(svc) -> None:
    service = _service(svc)
    user = AudienceUser(telegram_user_id=1, username="a", first_name="A")
    service._apply_score(user)
    assert 0 <= user.score <= 100
    comps = service.score_components(user)
    assert {c["key"] for c in comps} == {"username", "name", "not_bot", "premium"}
    assert user.score_reason


async def test_preview_scan(svc) -> None:
    provider = fake_audience_provider(count=5)
    service = _service(svc, provider)
    source = await service.add_source(reference="@x")
    preview = await service.preview_scan(source.id)
    assert preview.source_id == source.id
    assert preview.account_label
    assert preview.notes


async def test_no_account_raises(svc) -> None:
    # Delete the only account, then scanning must fail with a friendly error.
    from sqlalchemy import delete

    await svc.execute(delete(UserSession))
    await svc.flush()
    service = _service(svc)
    source = await service.add_source(reference="@x")
    with pytest.raises(AudienceServiceError):
        await service.preview_scan(source.id)
