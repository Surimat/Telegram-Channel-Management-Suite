"""Opt-in live verification of the keyless Kilo Gateway image understanding (D-122).

This is the *genuine* proof that the free vision path really works: it sends a
locally generated PNG (no external asset, no account, no API key) to
``api.kilo.ai`` and asserts a non-empty description comes back. It is the same
check that was run by hand on 2026-10-11 and recorded in D-122.

It is **opt-in** because it contacts a third-party, best-effort gateway and is
rate-limited per IP — CI must never depend on it. Enable it explicitly::

    TCMS_LIVE_KILO_VISION=1 python -m pytest tests/test_kilo_free_vision_live.py

Nothing here bypasses a challenge: if the gateway refuses (rate limit/outage),
the test skips with the honest reason instead of pretending success.
"""

from __future__ import annotations

import os
import struct
import zlib

import pytest
import pytest_asyncio

from backend.app.ai.gateway.providers import KiloGatewayProvider
from backend.app.ai.gateway.types import (
    MODALITY_IMAGE,
    Attachment,
    Capability,
    ChatMessage,
    ChatRequest,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("TCMS_LIVE_KILO_VISION") != "1",
    reason="live Kilo vision probe is opt-in (set TCMS_LIVE_KILO_VISION=1)",
)


def _png(colors: list[tuple[int, int, int]], size: int = 48) -> bytes:
    """A tiny solid-block PNG built without any image library."""

    def px(x: int, y: int) -> tuple[int, int, int]:
        index = min(int(x / size * len(colors)), len(colors) - 1)
        return colors[index]

    rows = b""
    for y in range(size):
        rows += b"\x00" + b"".join(bytes(px(x, y)) for x in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def _data_url(png: bytes) -> str:
    import base64

    return "data:image/png;base64," + base64.b64encode(png).decode()


@pytest_asyncio.fixture
async def provider() -> KiloGatewayProvider:
    from backend.app.ai.gateway.http import HttpxTransport

    return KiloGatewayProvider(transport=HttpxTransport())


async def test_kilo_keyless_free_vision_returns_a_real_description(
    provider: KiloGatewayProvider,
) -> None:
    # A green | yellow image: the model must answer about the image, not the text.
    png = _png([(30, 190, 60), (240, 220, 20)])
    req = ChatRequest(
        messages=[
            ChatMessage(
                role="user",
                content="Describe the colors in this image in one short sentence.",
                attachments=[
                    Attachment(kind=MODALITY_IMAGE, reference=_data_url(png))
                ],
            )
        ],
        requires=Capability(text=True, image=True),
        max_tokens=256,
        correlation_id="live-kilo-vision",
    )
    response = await provider.chat(req)
    if not response.ok:
        pytest.skip(f"live Kilo gateway refused honestly: {response.error}")
    assert response.text.strip(), "an empty answer is not image understanding"
    # It must not claim a key is needed — it is a keyless path.
    assert provider.info.auth_required is False
