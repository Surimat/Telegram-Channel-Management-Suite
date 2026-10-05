"""LAN peer discovery (pure helpers + best-effort UDP broadcast).

Discovery has two sources, merged by :func:`merge_peers`:

* **UDP broadcast** on the local network — a small JSON probe sent to the
  configured port. Firewalls often block this, which is fine: the owner can add
  **static peers** by host:port instead.
* **Static peers** from configuration.

A discovered peer is only ever a *proposal*. Nothing is trusted until the owner
pairs it (see :mod:`backend.app.mesh.pairing`).
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field

#: UDP port used for the discovery probe (kept out of the app HTTP port range).
DISCOVERY_PORT = 45678
PROBE_MAGIC = "tcms-mesh-probe/1"


@dataclass(slots=True)
class DiscoveryPeer:
    """A peer seen on the network (not yet trusted)."""

    node_id: str
    name: str = ""
    host: str = ""
    port: int = 0
    capabilities: list[str] = field(default_factory=list)
    priority: int = 0
    version: str = ""


def build_probe_payload(
    *,
    node_id: str,
    name: str,
    port: int,
    capabilities: list[str] | None = None,
    priority: int = 0,
    version: str = "",
) -> bytes:
    """Serialise a discovery probe (no secrets)."""
    return json.dumps(
        {
            "magic": PROBE_MAGIC,
            "node_id": node_id,
            "name": name,
            "port": int(port),
            "capabilities": list(capabilities or []),
            "priority": int(priority),
            "version": version,
        }
    ).encode("utf-8")


def parse_probe_payload(data: bytes, *, host: str = "") -> DiscoveryPeer | None:
    """Parse a discovery probe; return None for anything malformed."""
    try:
        payload = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("magic") != PROBE_MAGIC:
        return None
    node_id = str(payload.get("node_id", "") or "")
    if not node_id:
        return None
    port = payload.get("port", 0)
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 0
    return DiscoveryPeer(
        node_id=node_id,
        name=str(payload.get("name", "") or ""),
        host=host,
        port=port,
        capabilities=[str(c) for c in payload.get("capabilities", []) or []],
        priority=int(payload.get("priority", 0) or 0),
        version=str(payload.get("version", "") or ""),
    )


def parse_static_peers(raw: str) -> list[tuple[str, int]]:
    """Parse ``host:port,host:port`` into a list of (host, port)."""
    peers: list[tuple[str, int]] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        host, _, port_text = part.rpartition(":")
        if not host or not port_text.isdigit():
            continue
        peers.append((host, int(port_text)))
    return peers


def _peer_key(peer: DiscoveryPeer) -> str:
    return peer.node_id or f"{peer.host}:{peer.port}"


def merge_peers(*groups: list[DiscoveryPeer]) -> list[DiscoveryPeer]:
    """Merge discovery results, keeping the first sighting of each peer.

    Peers with a node id are keyed by it; static (id-less) peers are keyed by
    address so they are not silently dropped.
    """
    merged: dict[str, DiscoveryPeer] = {}
    for group in groups:
        for peer in group:
            key = _peer_key(peer)
            if key and key not in merged:
                merged[key] = peer
    return list(merged.values())


def broadcast_probe(
    payload: bytes, *, port: int = DISCOVERY_PORT, timeout: float = 0.3
) -> list[DiscoveryPeer]:
    """Send a UDP broadcast and collect replies (best-effort, may find nothing)."""
    found: list[DiscoveryPeer] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sock.sendto(payload, ("255.255.255.255", port))
        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except (TimeoutError, OSError):
                break
            peer = parse_probe_payload(data, host=addr[0])
            if peer is not None:
                found.append(peer)
    except OSError:
        return []
    finally:
        sock.close()
    return found


__all__ = [
    "DISCOVERY_PORT",
    "PROBE_MAGIC",
    "DiscoveryPeer",
    "broadcast_probe",
    "build_probe_payload",
    "merge_peers",
    "parse_probe_payload",
    "parse_static_peers",
]
