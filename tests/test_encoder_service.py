"""v1.1 lightweight-model install experience tests (no network, no torch).

The transport is injected and the official asset list is replaced with tiny
files, so the whole install → verify → honest-check flow runs without touching
the network or downloading the real 115 MB model.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.app.ai.encoder import EncoderClassifier
from backend.app.services.backup_backends.http import HttpResponse
from backend.app.services.encoder_service import (
    OFFICIAL_ASSETS,
    EncoderService,
    ModelAsset,
    human_size,
)

FAKE_ASSETS = (
    ModelAsset("config.json", 2, hashlib.sha256(b"{}").hexdigest()),
    ModelAsset("vocab.txt", 4, hashlib.sha256(b"abcd").hexdigest()),
)


def _transport_for(files: dict[str, bytes], *, status: int = 200):
    def _transport(method: str, url: str, headers: dict[str, str], body: bytes | None):
        name = url.rsplit("/", 1)[-1]
        if name not in files:
            return HttpResponse(status=404, body=b"", headers={})
        return HttpResponse(status=status, body=files[name], headers={})

    return _transport


def test_human_size_formats() -> None:
    assert human_size(512) == "512 Б"
    assert human_size(2048) == "2.0 КБ"
    assert human_size(5 * 1024 * 1024) == "5.0 МБ"


@pytest.mark.asyncio
async def test_status_reports_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("backend.app.services.encoder_service.OFFICIAL_ASSETS", FAKE_ASSETS)
    from backend.app.db.session import init_models, session_scope

    await init_models()
    async with session_scope() as db:
        service = EncoderService(db)
        status = await service.status()
        assert status.installed is False
        assert status.ready is False
        assert status.missing == ["config.json", "vocab.txt"]
        assert status.how_to_fix


@pytest.mark.asyncio
async def test_install_rejects_bad_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("backend.app.services.encoder_service.OFFICIAL_ASSETS", FAKE_ASSETS)
    from backend.app.db.session import init_models, session_scope

    await init_models()
    async with session_scope() as db:
        service = EncoderService(
            db, transport=_transport_for({"config.json": b"XX", "vocab.txt": b"abcd"})
        )
        result = await service.install()
        assert result.ok is False
        assert "целостност" in result.message.lower()


@pytest.mark.asyncio
async def test_install_never_claims_success_without_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The runtime (torch/transformers) is absent in CI, so the files verify but
    # the honest load check fails: install must report that truthfully.
    monkeypatch.setattr("backend.app.services.encoder_service.OFFICIAL_ASSETS", FAKE_ASSETS)
    from backend.app.db.session import init_models, session_scope

    await init_models()
    async with session_scope() as db:
        service = EncoderService(
            db, transport=_transport_for({"config.json": b"{}", "vocab.txt": b"abcd"})
        )
        result = await service.install()
        # Files are on disk…
        assert (service.model_dir / "config.json").is_file()
        # …but the result is honest about the runtime.
        assert result.ok is False
        assert result.status.installed is True
        assert "не запускается" in result.message.lower() or "библиотек" in result.message.lower()


@pytest.mark.asyncio
async def test_download_failure_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("backend.app.services.encoder_service.OFFICIAL_ASSETS", FAKE_ASSETS)
    from backend.app.db.session import init_models, session_scope

    await init_models()
    async with session_scope() as db:
        service = EncoderService(db, transport=_transport_for({}, status=500))
        result = await service.install()
        assert result.ok is False
        assert "скачать" in result.message.lower()


@pytest.mark.asyncio
async def test_remove_deletes_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.app.services.encoder_service.OFFICIAL_ASSETS", FAKE_ASSETS)
    from backend.app.db.session import init_models, session_scope

    await init_models()
    async with session_scope() as db:
        service = EncoderService(
            db, transport=_transport_for({"config.json": b"{}", "vocab.txt": b"abcd"})
        )
        await service.install()
        assert service.model_dir.is_dir()
        status = await service.remove()
        assert service.model_dir.is_dir() is False
        assert status.installed is False


def test_official_assets_are_the_real_ones() -> None:
    # Guard: the shipped list must stay the official ruBERT-tiny2 files, not the
    # test fakes. This is what the installer verifies against.
    names = {a.name for a in OFFICIAL_ASSETS}
    assert names == {
        "config.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "vocab.txt",
        "tokenizer.json",
        "model.safetensors",
    }


class _FakeBackend:
    """A deterministic encoder backend that replaces the hashing embedder."""

    name = "fake-rubert"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    @property
    def available(self) -> bool:
        return True

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors.get(t, [0.0, 0.0, 0.0]) for t in texts]


def test_encoder_classifier_uses_backend_embeddings() -> None:
    from backend.app.ai.encoder import PROTOTYPES

    # Give each prototype a distinct axis so the nearest neighbour is clear.
    vectors = {
        p.text: [1.0 if i == idx else 0.0 for i in range(len(PROTOTYPES))]
        for idx, p in enumerate(PROTOTYPES)
    }
    target = PROTOTYPES[0]
    backend = _FakeBackend(vectors)
    classifier = EncoderClassifier(backend=backend)  # type: ignore[arg-type]
    result = classifier.classify(target.text)
    assert result.model == "fake-rubert"
    assert result.category == target.category
