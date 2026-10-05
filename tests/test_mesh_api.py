"""LAN Mesh API tests (v1.3): status, discovery, pairing, leases."""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def mesh_client() -> AsyncClient:
    from backend.app.api.deps import get_mesh_service
    from backend.app.core.config import Settings, get_settings
    from backend.app.db.session import init_models
    from backend.app.main import create_app
    from backend.app.mesh.service import MeshService
    from backend.app.mesh.transport import RecordingTransport

    await init_models()
    settings = Settings(
        mesh_enabled=True,
        mesh_mode="lan_mesh",
        mesh_node_name="API PC",
        mesh_capabilities="telegram,ai",
        mesh_shared_secret="shared",
        mesh_discovery_enabled=False,
    )
    transport = RecordingTransport()

    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.app.db.session import get_session

    def _service(session: AsyncSession = Depends(get_session)) -> MeshService:
        return MeshService(session, settings=settings, transport=transport)

    app = create_app()
    app.dependency_overrides[get_mesh_service] = _service
    app.dependency_overrides[get_settings] = lambda: settings
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def test_status_endpoint(mesh_client: AsyncClient) -> None:
    resp = await mesh_client.get("/api/v1/mesh/status")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "lan_mesh"
    assert "telegram" in data["capabilities"]
    # No secret is ever returned.
    assert "shared" not in resp.text


async def test_pairing_and_peer_list(mesh_client: AsyncClient) -> None:
    code = await mesh_client.post("/api/v1/mesh/pairing-code")
    assert code.status_code == 201
    pair = await mesh_client.post(
        "/api/v1/mesh/pair",
        json={
            "code": code.json()["code"],
            "node_id": "mesh-peer",
            "host": "10.0.0.9",
            "port": 8002,
            "name": "Other PC",
            "capabilities": ["telegram"],
        },
    )
    assert pair.status_code == 200, pair.text
    assert pair.json()["trusted"] is True
    assert "credential" not in pair.text

    peers = await mesh_client.get("/api/v1/mesh/peers?trusted=true")
    assert peers.json()["total"] == 1


async def test_pairing_note_never_leaks_a_secret(mesh_client: AsyncClient) -> None:
    from backend.app.mesh.pairing import derive_shared_secret

    code = (await mesh_client.post("/api/v1/mesh/pairing-code")).json()["code"]
    pair = await mesh_client.post(
        "/api/v1/mesh/pair",
        json={"code": code, "node_id": "mesh-peer", "host": "10.0.0.9", "port": 8002},
    )
    assert pair.status_code == 200, pair.text
    derived = derive_shared_secret("shared", code)
    assert derived not in pair.text
    assert "Секрет" not in pair.text


async def test_ping_requires_the_mesh_secret(mesh_client: AsyncClient) -> None:
    denied = await mesh_client.post("/api/v1/mesh/ping", json={"from_node_id": "x"})
    assert denied.status_code == 401
    ok = await mesh_client.post(
        "/api/v1/mesh/ping", json={"from_node_id": "x"}, headers={"X-Mesh-Secret": "shared"}
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True


async def test_manual_peer_and_unpair(mesh_client: AsyncClient) -> None:
    created = await mesh_client.post(
        "/api/v1/mesh/peers/manual", json={"host": "10.0.0.5", "port": 8003}
    )
    assert created.status_code == 201, created.text
    peer_id = created.json()["id"]
    removed = await mesh_client.delete(f"/api/v1/mesh/peers/{peer_id}")
    assert removed.status_code == 204


async def test_elect_and_lease_endpoints(mesh_client: AsyncClient) -> None:
    elect = await mesh_client.post("/api/v1/mesh/elect")
    assert elect.status_code == 200
    assert elect.json()["coordinator_id"]

    acquired = await mesh_client.post(
        "/api/v1/mesh/leases/acquire",
        json={"job_id": "job-1", "kind": "reaction", "requirements": {"capability": "telegram"}},
    )
    assert acquired.status_code == 200, acquired.text
    lease = acquired.json()
    assert lease["fencing_token"] >= 1

    committed = await mesh_client.post(
        "/api/v1/mesh/leases/complete",
        json={"job_id": "job-1", "owner": lease["lease_owner"], "token": lease["fencing_token"]},
    )
    assert committed.json()["committed"] is True

    leases = await mesh_client.get("/api/v1/mesh/leases")
    assert leases.json()["total"] == 1
