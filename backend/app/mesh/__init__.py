"""LAN Mesh: an offline, no-VPS control plane for several of the owner's PCs.

This package contains the pure mesh logic (node identity, discovery, election,
leases with fencing, pairing credentials, capability matching and poller
ownership). The network transport and persistence live in :mod:`.service` and the
HTTP API; the algorithms here are deliberately dependency-free and unit-testable
without a network (D-001 style separation).
"""

from backend.app.mesh.capability import (
    capability_matches,
    parse_capabilities,
    serialize_capabilities,
)
from backend.app.mesh.discovery import (
    DiscoveryPeer,
    build_probe_payload,
    merge_peers,
    parse_static_peers,
)
from backend.app.mesh.election import ElectionCandidate, elect_coordinator
from backend.app.mesh.identity import (
    build_node_identity,
    derive_node_id,
    resolve_capabilities,
)
from backend.app.mesh.lease import LeaseGrant, can_commit, should_reclaim

__all__ = [
    "DiscoveryPeer",
    "ElectionCandidate",
    "LeaseGrant",
    "build_node_identity",
    "build_probe_payload",
    "can_commit",
    "capability_matches",
    "derive_node_id",
    "elect_coordinator",
    "merge_peers",
    "parse_capabilities",
    "parse_static_peers",
    "resolve_capabilities",
    "serialize_capabilities",
    "should_reclaim",
]
