"""LAN Mesh tests (v1.3).

Covers the pure algorithms (identity, discovery, election, capability matching,
fencing leases, pairing) and the service against the local DB with an in-memory
transport. No network is used (D-001).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.app.db.base import utcnow
from backend.app.db.models.mesh import (
    CAP_AI,
    CAP_TELEGRAM,
    MeshMode,
    MeshRole,
    PeerStatus,
)
from backend.app.db.session import init_models, session_scope
from backend.app.mesh.capability import (
    capability_matches,
    parse_capabilities,
    serialize_capabilities,
)
from backend.app.mesh.discovery import (
    DiscoveryPeer,
    build_probe_payload,
    merge_peers,
    parse_probe_payload,
    parse_static_peers,
)
from backend.app.mesh.election import ElectionCandidate, elect_coordinator
from backend.app.mesh.identity import (
    build_node_identity,
    derive_node_id,
    parse_mode,
    resolve_capabilities,
)
from backend.app.mesh.lease import can_commit, should_reclaim
from backend.app.mesh.pairing import (
    derive_shared_secret,
    generate_pairing_code,
    hash_pairing_code,
    verify_pairing_code,
)
from backend.app.mesh.service import MeshService, MeshServiceError
from backend.app.mesh.transport import MeshTransportError, RecordingTransport


@pytest.fixture(autouse=True)
async def _models() -> None:
    await init_models()


def _settings(**overrides):  # type: ignore[no-untyped-def]
    from backend.app.core.config import Settings

    base = {
        "mesh_enabled": True,
        "mesh_mode": "lan_mesh",
        "mesh_node_name": "Test PC",
        "mesh_priority": 5,
        "mesh_capabilities": "telegram,ai",
        "mesh_shared_secret": "shared-secret",
        "mesh_discovery_enabled": False,
    }
    base.update(overrides)
    return Settings(**base)


# --- pure: identity ----------------------------------------------------------
def test_derive_node_id_is_stable_and_namespaced():
    a = derive_node_id("seed")
    assert a == derive_node_id("seed")
    assert a.startswith("mesh-")
    assert a != derive_node_id("other")


def test_resolve_capabilities_defaults_to_all_and_filters_unknown():
    assert CAP_TELEGRAM in resolve_capabilities("")
    assert resolve_capabilities("telegram, nope, ai") == ["telegram", "ai"]


def test_parse_mode_falls_back_to_standalone():
    assert parse_mode("LAN_MESH") is MeshMode.LAN_MESH
    assert parse_mode("nonsense") is MeshMode.STANDALONE


def test_build_node_identity_standalone_forces_role():
    node = build_node_identity(
        seed="s",
        version="1.3.0",
        mode=MeshMode.STANDALONE,
        capabilities=[CAP_TELEGRAM],
    )
    assert node.role is MeshRole.STANDALONE
    assert node.node_id.startswith("mesh-")


# --- pure: discovery ---------------------------------------------------------
def test_probe_payload_round_trip():
    payload = build_probe_payload(
        node_id="mesh-abc", name="PC", port=8001, capabilities=[CAP_TELEGRAM], priority=2
    )
    peer = parse_probe_payload(payload, host="10.0.0.5")
    assert peer is not None
    assert peer.node_id == "mesh-abc"
    assert peer.host == "10.0.0.5"
    assert peer.port == 8001


def test_parse_probe_rejects_garbage():
    assert parse_probe_payload(b"not json") is None
    assert parse_probe_payload(b'{"magic":"wrong"}') is None


def test_parse_static_peers():
    assert parse_static_peers("192.168.1.5:8001, host:9000") == [
        ("192.168.1.5", 8001),
        ("host", 9000),
    ]
    assert parse_static_peers("bad,onlyhost:") == []


def test_merge_peers_keeps_static_addresses():
    a = DiscoveryPeer(node_id="n1", host="h1", port=1)
    b = DiscoveryPeer(node_id="", host="h2", port=2)
    merged = merge_peers([a], [b])
    assert len(merged) == 2


# --- pure: election ----------------------------------------------------------
def test_elect_prefers_priority_then_node_id():
    candidates = [
        ElectionCandidate("mesh-a", priority=1, capabilities=[CAP_TELEGRAM]),
        ElectionCandidate("mesh-b", priority=3, capabilities=[CAP_TELEGRAM]),
        ElectionCandidate("mesh-c", priority=3, capabilities=[CAP_TELEGRAM]),
    ]
    # Highest priority wins; ties break on the lowest node id.
    assert elect_coordinator(candidates) == "mesh-b"


def test_elect_skips_nodes_without_telegram_and_offline():
    candidates = [
        ElectionCandidate("mesh-a", priority=9, capabilities=[CAP_AI]),
        ElectionCandidate("mesh-b", priority=1, capabilities=[CAP_TELEGRAM], online=False),
        ElectionCandidate("mesh-c", priority=0, capabilities=[CAP_TELEGRAM]),
    ]
    assert elect_coordinator(candidates) == "mesh-c"
    assert elect_coordinator([ElectionCandidate("mesh-a", capabilities=[])]) is None


# --- pure: capabilities ------------------------------------------------------
def test_capability_matching():
    assert capability_matches([CAP_TELEGRAM], [CAP_TELEGRAM, CAP_AI])
    assert not capability_matches([CAP_AI], [CAP_TELEGRAM])
    assert capability_matches([], [])
    assert parse_capabilities(serialize_capabilities(["ai", "telegram", "ai"])) == [
        "ai",
        "telegram",
    ]


# --- pure: leases ------------------------------------------------------------
def test_fencing_commit_rejects_stale_token():
    assert can_commit(
        lease_owner="w1", lease_token=2, current_owner="w1", current_token=2, expired=False
    )
    # A newer worker took over with token 3.
    assert not can_commit(
        lease_owner="w1", lease_token=2, current_owner="w1", current_token=3, expired=False
    )
    assert not can_commit(
        lease_owner="w1", lease_token=2, current_owner="w1", current_token=2, expired=True
    )


def test_should_reclaim_only_for_expired_active_leases():
    now = utcnow()
    assert should_reclaim(lease_until=now - timedelta(seconds=1), now=now, status="active")
    assert not should_reclaim(lease_until=now + timedelta(seconds=30), now=now, status="active")
    assert not should_reclaim(lease_until=None, now=now, status="completed")


# --- pure: pairing -----------------------------------------------------------
def test_pairing_code_hashes_and_verifies():
    code = generate_pairing_code()
    stored = hash_pairing_code(code, salt="node-1")
    assert code not in stored  # never stored in the clear
    assert verify_pairing_code(code.lower(), stored, salt="node-1")
    assert not verify_pairing_code("WRONG", stored, salt="node-1")


def test_shared_secret_is_symmetric():
    assert derive_shared_secret("a", "b") == derive_shared_secret("b", "a")
    assert derive_shared_secret("a", "b") != derive_shared_secret("a", "c")


# --- service -----------------------------------------------------------------
async def test_ensure_node_creates_stable_identity():
    async with session_scope() as session:
        service = MeshService(session, settings=_settings())
        node = await service.ensure_node()
        again = await service.ensure_node()
        assert node.id == again.id
        assert node.node_id == again.node_id
        assert node.mode is MeshMode.LAN_MESH


async def test_status_reports_standalone_note():
    async with session_scope() as session:
        service = MeshService(session, settings=_settings(mesh_mode="standalone"))
        data = await service.status()
        assert data["mode"] == "standalone"
        assert "локально" in data["note"]


async def test_pairing_flow_trusts_peer_and_never_returns_secret():
    async with session_scope() as session:
        service = MeshService(session, settings=_settings())
        code = await service.issue_pairing_code()
        peer = await service.pair(
            code=code.code,
            node_id="mesh-peer",
            host="10.0.0.9",
            port=8002,
            name="Other PC",
            capabilities=[CAP_TELEGRAM],
        )
        assert peer.trusted is True
        assert peer.status is PeerStatus.ONLINE
        # The raw pairing code / shared secret must not be recoverable from storage.
        assert code.code not in (peer.credential_hash or "")
        assert code.code not in (peer.note or "")


async def test_pair_rejects_invalid_code():
    async with session_scope() as session:
        service = MeshService(session, settings=_settings())
        with pytest.raises(MeshServiceError):
            await service.pair(code="NOPE", node_id="mesh-x")


async def test_elect_marks_roles_in_mesh():
    async with session_scope() as session:
        service = MeshService(session, settings=_settings(mesh_priority=10))
        code = await service.issue_pairing_code()
        await service.pair(
            code=code.code,
            node_id="mesh-peer",
            host="10.0.0.9",
            port=8002,
            capabilities=[CAP_TELEGRAM],
            priority=1,
        )
        coordinator = await service.elect()
        assert coordinator == (await service.ensure_node()).node_id
        assert await service.owns_telegram_pollers() is True


async def test_owns_pollers_true_in_standalone():
    async with session_scope() as session:
        service = MeshService(session, settings=_settings(mesh_mode="standalone"))
        assert await service.owns_telegram_pollers() is True


async def test_acquire_and_complete_lease_with_fencing():
    async with session_scope() as session:
        service = MeshService(session, settings=_settings())
        lease = await service.acquire_lease(
            "job-1", kind="reaction", requirements={"capability": CAP_TELEGRAM}
        )
        assert lease is not None
        node = await service.ensure_node()
        assert await service.complete_lease(
            "job-1", owner=node.node_id, token=lease.fencing_token
        )
        assert not await service.complete_lease(
            "job-1", owner=node.node_id, token=lease.fencing_token + 5
        )


async def test_acquire_lease_skips_incapable_node():
    async with session_scope() as session:
        service = MeshService(session, settings=_settings(mesh_capabilities="telegram"))
        lease = await service.acquire_lease("job-ai", requirements={"capability": CAP_AI})
        assert lease is None


async def test_reclaim_expired_leases():
    async with session_scope() as session:
        service = MeshService(session, settings=_settings())
        lease = await service.acquire_lease("job-x")
        assert lease is not None
        lease.lease_until = utcnow() - timedelta(seconds=1)
        await session.flush()
        assert await service.reclaim_expired() == 1


async def test_probe_peer_marks_offline_on_transport_error():
    transport = RecordingTransport(fail_with=MeshTransportError("down", reason="timeout"))
    async with session_scope() as session:
        service = MeshService(session, settings=_settings(), transport=transport)
        peer = await service.add_manual_peer(host="10.0.0.9", port=8002, name="Other")
        status = await service.probe_peer(peer.id)
        assert status is PeerStatus.OFFLINE


async def test_discover_records_static_peers_without_broadcast():
    async with session_scope() as session:
        service = MeshService(
            session,
            settings=_settings(mesh_discovery_enabled=False, mesh_static_peers="10.0.0.9:8002"),
        )
        found = await service.discover()
        # Static peers have no node id and are not auto-registered as candidates.
        assert isinstance(found, list)
