"""LAN Mesh service: identity, discovery, pairing, election and leases.

The service owns no network protocol of its own; it delegates peer requests to a
:class:`~backend.app.mesh.transport.MeshTransport` so tests run entirely offline.
All state lives in the local database (never a shared SQLite over a network
share), which keeps a single writer per computer.
"""

from __future__ import annotations

import json
import socket
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.db.base import utcnow
from backend.app.db.models.mesh import (
    CAP_TELEGRAM,
    MODE_TITLES,
    PEER_STATUS_TITLES,
    LeaseStatus,
    MeshLease,
    MeshMode,
    MeshNode,
    MeshPeer,
    MeshRole,
    PairingCode,
    PeerStatus,
)
from backend.app.db.repositories.mesh import (
    MeshLeaseRepository,
    MeshNodeRepository,
    MeshPeerRepository,
    PairingCodeRepository,
)
from backend.app.mesh.capability import (
    capability_matches,
    parse_capabilities,
    serialize_capabilities,
)
from backend.app.mesh.discovery import (
    DiscoveryPeer,
    broadcast_probe,
    build_probe_payload,
    merge_peers,
    parse_static_peers,
)
from backend.app.mesh.election import ElectionCandidate, elect_coordinator
from backend.app.mesh.identity import (
    build_node_identity,
    default_node_name,
    parse_mode,
    resolve_capabilities,
)
from backend.app.mesh.lease import can_commit, next_fencing_token, should_reclaim
from backend.app.mesh.pairing import (
    generate_pairing_code,
    hash_pairing_code,
)
from backend.app.mesh.transport import (
    HttpMeshTransport,
    MeshTransport,
    MeshTransportError,
    PeerAddress,
)

MODULE = "mesh"

#: How long a pairing code stays valid.
PAIRING_CODE_TTL_SECONDS = 600


class MeshServiceError(RuntimeError):
    def __init__(self, message: str, *, how_to_fix: str = "", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix
        self.status_code = status_code


def _local_ip() -> str:
    """Best-effort local network address (never fails; "" when unknown)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


class MeshService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        transport: MeshTransport | None = None,
        now=None,  # type: ignore[no-untyped-def]
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.nodes = MeshNodeRepository(session)
        self.peers = MeshPeerRepository(session)
        self.codes = PairingCodeRepository(session)
        self.leases = MeshLeaseRepository(session)
        self.transport = transport or HttpMeshTransport()
        self._now = now or utcnow
        from backend.app import __version__ as _version

        self.version = _version

    def _now_dt(self):  # type: ignore[no-untyped-def]
        return self._now()

    # --- identity ------------------------------------------------------------
    async def ensure_node(self) -> MeshNode:
        """Return this computer's node row, creating it on first use."""
        node = await self.nodes.get_self()
        mode = parse_mode(self.settings.mesh_mode)
        name = self.settings.mesh_node_name.strip() or default_node_name()
        capabilities = resolve_capabilities(self.settings.mesh_capabilities)
        version = self.version
        identity = build_node_identity(
            seed=f"{name}|{socket.gethostname()}",
            version=version,
            mode=mode,
            capabilities=capabilities,
            priority=self.settings.mesh_priority,
            name=name,
            host=_local_ip(),
            port=self.settings.mesh_port or (self.settings.app_port + 1),
        )
        if node is None:
            node = MeshNode(
                node_id=identity.node_id,
                name=identity.name,
                version=identity.version,
                mode=identity.mode,
                role=identity.role,
                capabilities=serialize_capabilities(identity.capabilities),
                priority=identity.priority,
                host=identity.host,
                port=identity.port,
            )
            await self.nodes.add(node)
        else:
            # Keep the row in sync with configuration changes.
            node.name = identity.name
            node.mode = identity.mode
            node.capabilities = serialize_capabilities(identity.capabilities)
            node.priority = identity.priority
            node.host = identity.host
            node.port = identity.port
            if node.mode is MeshMode.STANDALONE:
                node.role = MeshRole.STANDALONE
        node.last_heartbeat = self._now_dt()
        await self.session.commit()
        return node

    async def status(self) -> dict:
        node = await self.ensure_node()
        all_peers = await self.peers.list_all()
        online = [p for p in all_peers if p.status is PeerStatus.ONLINE]
        trusted = [p for p in all_peers if p.trusted]
        return {
            "enabled": self.settings.mesh_enabled,
            "mode": str(node.mode),
            "mode_label": MODE_TITLES.get(node.mode, str(node.mode)),
            "role": str(node.role),
            "node_id": node.node_id,
            "name": node.name,
            "capabilities": parse_capabilities(node.capabilities),
            "priority": node.priority,
            "host": node.host,
            "port": node.port,
            "coordinator_id": node.coordinator_id,
            "peers_total": len(all_peers),
            "peers_trusted": len(trusted),
            "peers_online": len(online),
            "discovery_enabled": self.settings.mesh_discovery_enabled,
            "note": (
                "Один компьютер: все задачи выполняются локально."
                if node.mode is MeshMode.STANDALONE
                else "Компьютеры объединяются в локальной сети. Общие данные "
                "синхронизируются, но SQLite не открывается по сети."
            ),
        }

    # --- discovery -----------------------------------------------------------
    async def discover(self, *, register: bool = True) -> list[DiscoveryPeer]:
        """Look for peers on the LAN (broadcast + static) and record candidates."""
        node = await self.ensure_node()
        groups: list[list[DiscoveryPeer]] = []
        if self.settings.mesh_discovery_enabled:
            payload = build_probe_payload(
                node_id=node.node_id,
                name=node.name,
                port=node.port,
                capabilities=parse_capabilities(node.capabilities),
                priority=node.priority,
                version=node.version,
            )
            groups.append(broadcast_probe(payload))
        static: list[DiscoveryPeer] = []
        for host, port in parse_static_peers(self.settings.mesh_static_peers):
            static.append(DiscoveryPeer(node_id="", host=host, port=port))
        groups.append(static)
        found = [p for p in merge_peers(*groups) if p.node_id != node.node_id]

        if register:
            for peer in found:
                if peer.node_id:
                    await self._record_candidate(peer)
            await self.session.commit()
        return found

    async def _record_candidate(self, peer: DiscoveryPeer) -> MeshPeer:
        existing = await self.peers.get_by_node_id(peer.node_id)
        if existing is not None:
            existing.name = peer.name or existing.name
            existing.host = peer.host or existing.host
            existing.port = peer.port or existing.port
            existing.capabilities = serialize_capabilities(peer.capabilities)
            existing.priority = peer.priority
            existing.version = peer.version or existing.version
            return existing
        row = MeshPeer(
            node_id=peer.node_id,
            name=peer.name,
            version=peer.version,
            capabilities=serialize_capabilities(peer.capabilities),
            priority=peer.priority,
            host=peer.host,
            port=peer.port,
            trusted=False,
            status=PeerStatus.UNKNOWN,
            note="Найден в сети. Подтвердите сопряжение, чтобы доверять.",
        )
        return await self.peers.add(row)

    async def add_manual_peer(self, *, host: str, port: int, name: str = "") -> MeshPeer:
        """Record a peer by address when broadcast is blocked."""
        host = (host or "").strip()
        if not host or not (0 < int(port) < 65536):
            raise MeshServiceError(
                "Укажите адрес и порт компьютера.",
                how_to_fix="Например: 192.168.1.20:8001.",
            )
        row = MeshPeer(
            node_id="",
            name=name.strip() or host,
            host=host,
            port=int(port),
            trusted=False,
            status=PeerStatus.UNKNOWN,
            note="Добавлен вручную. Подтвердите сопряжение.",
        )
        await self.peers.add(row)
        await self.session.commit()
        return row

    # --- pairing -------------------------------------------------------------
    async def issue_pairing_code(self) -> PairingCode:
        node = await self.ensure_node()
        code = generate_pairing_code()
        row = PairingCode(
            code=code,
            issued_by=node.node_id,
            expires_at=self._now_dt() + timedelta(seconds=PAIRING_CODE_TTL_SECONDS),
            used=False,
        )
        await self.codes.add(row)
        await self.session.commit()
        return row

    async def pair(
        self,
        *,
        code: str,
        node_id: str = "",
        host: str = "",
        port: int = 0,
        name: str = "",
        capabilities: list[str] | None = None,
        priority: int = 0,
        version: str = "",
    ) -> MeshPeer:
        """Trust a peer after verifying the owner-shown pairing code."""
        node = await self.ensure_node()
        active = await self.codes.find_active(code.strip().upper(), now=self._now_dt())
        if active is None:
            raise MeshServiceError(
                "Код сопряжения недействителен или истёк.",
                how_to_fix="Сформируйте новый код на этом компьютере и повторите.",
                status_code=409,
            )
        peer: MeshPeer | None = None
        if node_id:
            peer = await self.peers.get_by_node_id(node_id)
        if peer is None and host and port:
            for candidate in await self.peers.list_all():
                if candidate.host == host and candidate.port == port:
                    peer = candidate
                    break
        if peer is None:
            peer = MeshPeer(node_id=node_id, host=host, port=port)
            await self.peers.add(peer)

        # The raw pairing code is stored only as a salted hash; nothing derived
        # from a secret is persisted (the note is user-visible through the API).
        peer.credential_hash = hash_pairing_code(active.code, salt=node.node_id)
        peer.trusted = True
        peer.status = PeerStatus.ONLINE
        peer.last_seen = self._now_dt()
        peer.name = name or peer.name
        peer.host = host or peer.host
        peer.port = port or peer.port
        peer.version = version or peer.version
        peer.priority = int(priority)
        if capabilities is not None:
            peer.capabilities = serialize_capabilities(capabilities)
        peer.note = "Сопряжён с этим компьютером."

        active.used = True
        active.used_by = peer.node_id
        await self.session.commit()
        return peer

    async def unpair(self, peer_id: str) -> None:
        peer = await self.peers.get(peer_id)
        if peer is None:
            raise MeshServiceError("Компьютер не найден.", status_code=404)
        await self.peers.delete(peer)
        await self.session.commit()

    # --- election ------------------------------------------------------------
    async def elect(self) -> str | None:
        """Recompute the coordinator across self + trusted online peers."""
        node = await self.ensure_node()
        candidates = [
            ElectionCandidate(
                node_id=node.node_id,
                priority=node.priority,
                capabilities=parse_capabilities(node.capabilities),
                online=True,
            )
        ]
        for peer in await self.peers.list_all(trusted=True):
            candidates.append(
                ElectionCandidate(
                    node_id=peer.node_id,
                    priority=peer.priority,
                    capabilities=parse_capabilities(peer.capabilities),
                    online=peer.status is PeerStatus.ONLINE,
                )
            )
        coordinator = elect_coordinator(candidates, required_capability=CAP_TELEGRAM)
        if node.mode is not MeshMode.STANDALONE:
            node.role = (
                MeshRole.COORDINATOR if coordinator == node.node_id else MeshRole.WORKER
            )
            node.coordinator_id = "" if coordinator == node.node_id else (coordinator or "")
        await self.session.commit()
        return coordinator

    async def owns_telegram_pollers(self) -> bool:
        """Whether this node should own Telegram pollers (avoid double-polling)."""
        node = await self.ensure_node()
        if node.mode is MeshMode.STANDALONE:
            return True
        if not self.settings.mesh_enabled:
            return True
        return node.role is MeshRole.COORDINATOR

    # --- leases --------------------------------------------------------------
    async def acquire_lease(
        self, job_id: str, *, kind: str = "", requirements: dict | None = None
    ) -> MeshLease | None:
        """Lease a job to this node if it is free and this node is capable."""
        node = await self.ensure_node()
        req = requirements or {}
        required_cap = str(req.get("capability", "") or "")
        if required_cap and not capability_matches(
            [required_cap], parse_capabilities(node.capabilities)
        ):
            return None
        existing = await self.leases.active_for_job(job_id)
        if existing is not None:
            if not should_reclaim(
                lease_until=existing.lease_until,
                now=self._now_dt(),
                status=str(existing.status),
            ):
                return existing if existing.lease_owner == node.node_id else None
            existing.status = LeaseStatus.EXPIRED
            token = next_fencing_token(existing.fencing_token)
        else:
            token = 1
        lease = MeshLease(
            job_id=job_id,
            kind=kind,
            requirements=json.dumps(req),
            lease_owner=node.node_id,
            lease_until=self._now_dt() + timedelta(seconds=self.settings.mesh_lease_seconds),
            fencing_token=token,
            status=LeaseStatus.ACTIVE,
            attempts=(existing.attempts + 1) if existing is not None else 1,
        )
        await self.leases.add(lease)
        await self.session.commit()
        return lease

    async def complete_lease(
        self, job_id: str, *, owner: str, token: int, error: str = ""
    ) -> bool:
        """Commit a result; a stale token (after failover) is rejected."""
        lease = await self.leases.active_for_job(job_id)
        if lease is None:
            return False
        expired = should_reclaim(
            lease_until=lease.lease_until, now=self._now_dt(), status=str(lease.status)
        )
        if not can_commit(
            lease_owner=owner,
            lease_token=token,
            current_owner=lease.lease_owner,
            current_token=lease.fencing_token,
            expired=expired,
        ):
            return False
        lease.status = LeaseStatus.COMPLETED if not error else LeaseStatus.RELEASED
        lease.error = error
        await self.session.commit()
        return True

    async def reclaim_expired(self) -> int:
        """Mark expired active leases so another worker may take them."""
        count = 0
        for lease in await self.leases.list_active():
            if should_reclaim(
                lease_until=lease.lease_until, now=self._now_dt(), status=str(lease.status)
            ):
                lease.status = LeaseStatus.EXPIRED
                count += 1
        if count:
            await self.session.commit()
        return count

    # --- peer heartbeat (network; best-effort) -------------------------------
    async def probe_peer(self, peer_id: str) -> PeerStatus:
        peer = await self.peers.get(peer_id)
        if peer is None:
            raise MeshServiceError("Компьютер не найден.", status_code=404)
        address = PeerAddress(host=peer.host, port=peer.port)
        secret = self.settings.mesh_shared_secret.get_secret_value()
        try:
            await self.transport.request(address, "/api/v1/mesh/ping", {}, secret=secret)
        except MeshTransportError:
            peer.status = PeerStatus.OFFLINE
            await self.session.commit()
            return PeerStatus.OFFLINE
        peer.status = PeerStatus.ONLINE
        peer.last_seen = self._now_dt()
        await self.session.commit()
        return PeerStatus.ONLINE

    async def peer_status_label(self, peer: MeshPeer) -> str:
        return PEER_STATUS_TITLES.get(peer.status, str(peer.status))


__all__ = ["MODULE", "MeshService", "MeshServiceError"]
