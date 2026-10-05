"""LAN Mesh router (v1.3).

Lets the owner see this computer's mesh identity, discover and pair peers on the
local network, and inspect/lease jobs. The control plane is fully offline: no
cloud service is involved. Pairing codes and shared secrets are never returned.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from backend.app.api.deps import get_mesh_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.mesh import (
    MeshLeaseAcquireIn,
    MeshLeaseCompleteIn,
    MeshLeaseListOut,
    MeshLeaseOut,
    MeshPairIn,
    MeshPeerListOut,
    MeshPeerManualIn,
    MeshPeerOut,
    MeshPingIn,
    MeshStatusOut,
    PairingCodeOut,
)
from backend.app.core.config import Settings, get_settings
from backend.app.core.security import constant_time_compare
from backend.app.mesh.capability import parse_capabilities
from backend.app.mesh.service import MeshService, MeshServiceError

router = APIRouter(prefix="/mesh", tags=["mesh"])


def _raise(exc: MeshServiceError) -> None:
    raise ApiError(exc.status_code, exc.message, exc.how_to_fix)


def _peer_out(service: MeshService, peer) -> MeshPeerOut:  # type: ignore[no-untyped-def]
    from backend.app.db.models.mesh import PEER_STATUS_TITLES

    return MeshPeerOut(
        id=peer.id,
        node_id=peer.node_id,
        name=peer.name,
        version=peer.version,
        capabilities=parse_capabilities(peer.capabilities),
        priority=peer.priority,
        host=peer.host,
        port=peer.port,
        trusted=peer.trusted,
        status=str(peer.status),
        status_label=PEER_STATUS_TITLES.get(peer.status, str(peer.status)),
        last_seen=peer.last_seen,
        note=peer.note,
    )


@router.get("/status", response_model=MeshStatusOut)
async def status(service: MeshService = Depends(get_mesh_service)) -> MeshStatusOut:
    return MeshStatusOut(**await service.status())


@router.get("/peers", response_model=MeshPeerListOut)
async def list_peers(
    trusted: bool | None = None, service: MeshService = Depends(get_mesh_service)
) -> MeshPeerListOut:
    peers = await service.peers.list_all(trusted=trusted)
    return MeshPeerListOut(
        items=[_peer_out(service, p) for p in peers], total=len(peers)
    )


@router.post("/discover", response_model=MeshPeerListOut)
async def discover(service: MeshService = Depends(get_mesh_service)) -> MeshPeerListOut:
    found = await service.discover()
    peers = await service.peers.list_all()
    return MeshPeerListOut(
        items=[_peer_out(service, p) for p in peers], total=len(peers) if found else 0
    )


@router.post("/peers/manual", response_model=MeshPeerOut, status_code=201)
async def add_manual(
    payload: MeshPeerManualIn, service: MeshService = Depends(get_mesh_service)
) -> MeshPeerOut:
    try:
        peer = await service.add_manual_peer(
            host=payload.host, port=payload.port, name=payload.name
        )
    except MeshServiceError as exc:
        _raise(exc)
    return _peer_out(service, peer)


@router.post("/pairing-code", response_model=PairingCodeOut, status_code=201)
async def issue_code(
    service: MeshService = Depends(get_mesh_service),
) -> PairingCodeOut:
    code = await service.issue_pairing_code()
    return PairingCodeOut(code=code.code, expires_at=code.expires_at)


@router.post("/pair", response_model=MeshPeerOut)
async def pair(
    payload: MeshPairIn, service: MeshService = Depends(get_mesh_service)
) -> MeshPeerOut:
    try:
        peer = await service.pair(
            code=payload.code,
            node_id=payload.node_id,
            host=payload.host,
            port=payload.port,
            name=payload.name,
            capabilities=payload.capabilities,
            priority=payload.priority,
            version=payload.version,
        )
    except MeshServiceError as exc:
        _raise(exc)
    return _peer_out(service, peer)


@router.delete("/peers/{peer_id}", status_code=204)
async def unpair(peer_id: str, service: MeshService = Depends(get_mesh_service)) -> None:
    try:
        await service.unpair(peer_id)
    except MeshServiceError as exc:
        _raise(exc)


@router.post("/peers/{peer_id}/probe", response_model=MeshPeerOut)
async def probe(
    peer_id: str, service: MeshService = Depends(get_mesh_service)
) -> MeshPeerOut:
    try:
        await service.probe_peer(peer_id)
    except MeshServiceError as exc:
        _raise(exc)
    peer = await service.peers.get(peer_id)
    return _peer_out(service, peer)


@router.post("/elect")
async def elect(service: MeshService = Depends(get_mesh_service)) -> dict[str, str]:
    coordinator = await service.elect()
    return {"coordinator_id": coordinator or ""}


@router.get("/leases", response_model=MeshLeaseListOut)
async def list_leases(
    service: MeshService = Depends(get_mesh_service),
) -> MeshLeaseListOut:
    leases = await service.leases.list_all()
    return MeshLeaseListOut(
        items=[
            MeshLeaseOut(
                id=lease.id,
                job_id=lease.job_id,
                kind=lease.kind,
                lease_owner=lease.lease_owner,
                lease_until=lease.lease_until,
                fencing_token=lease.fencing_token,
                status=str(lease.status),
                attempts=lease.attempts,
                error=lease.error,
            )
            for lease in leases
        ],
        total=len(leases),
    )


@router.post("/leases/acquire", response_model=MeshLeaseOut | None)
async def acquire_lease(
    payload: MeshLeaseAcquireIn, service: MeshService = Depends(get_mesh_service)
) -> MeshLeaseOut | None:
    lease = await service.acquire_lease(
        payload.job_id, kind=payload.kind, requirements=payload.requirements
    )
    if lease is None:
        return None
    return MeshLeaseOut(
        id=lease.id,
        job_id=lease.job_id,
        kind=lease.kind,
        lease_owner=lease.lease_owner,
        lease_until=lease.lease_until,
        fencing_token=lease.fencing_token,
        status=str(lease.status),
        attempts=lease.attempts,
        error=lease.error,
    )


@router.post("/leases/complete")
async def complete_lease(
    payload: MeshLeaseCompleteIn, service: MeshService = Depends(get_mesh_service)
) -> dict[str, bool]:
    ok = await service.complete_lease(
        payload.job_id, owner=payload.owner, token=payload.token, error=payload.error
    )
    return {"committed": ok}


@router.post("/leases/reclaim")
async def reclaim(service: MeshService = Depends(get_mesh_service)) -> dict[str, int]:
    return {"reclaimed": await service.reclaim_expired()}


@router.post("/ping")
async def ping(
    payload: MeshPingIn,
    x_mesh_secret: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Peer liveness endpoint, authenticated by the shared secret.

    When a mesh secret is configured, a request without it is rejected — so an
    unpaired host on the same network cannot use this as an open probe.
    """
    expected = settings.mesh_shared_secret.get_secret_value()
    if expected and not constant_time_compare(x_mesh_secret, expected):
        raise ApiError(401, "Запрос отклонён: неверный секрет сети.")
    return {"ok": True, "node_id": payload.from_node_id}
