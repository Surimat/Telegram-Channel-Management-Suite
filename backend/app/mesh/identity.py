"""Node identity for the LAN mesh (pure, no I/O).

The node id is stable for a machine: it is derived from a persistent seed so a
restart keeps the same identity, while two installs on the same host would still
differ by their seed. Nothing here is a secret.
"""

from __future__ import annotations

import hashlib
import socket
from dataclasses import dataclass

from backend.app.db.models.mesh import (
    ALL_CAPABILITIES,
    MeshMode,
    MeshRole,
)

#: Prefix that namespaces mesh node ids (so they are recognisable, not secret).
NODE_ID_PREFIX = "mesh"


def derive_node_id(seed: str) -> str:
    """Return a stable, non-secret node id for ``seed``."""
    digest = hashlib.sha256((seed or "").encode("utf-8")).hexdigest()
    return f"{NODE_ID_PREFIX}-{digest[:24]}"


def default_node_name() -> str:
    """A readable default name for this computer."""
    try:
        host = socket.gethostname()
    except OSError:  # pragma: no cover - extremely unusual
        host = ""
    return host or "Компьютер"


def parse_mode(value: str) -> MeshMode:
    try:
        return MeshMode((value or "").strip().lower())
    except ValueError:
        return MeshMode.STANDALONE


def resolve_capabilities(raw: str) -> list[str]:
    """Parse a comma-separated capability list; empty means "all"."""
    values = [part.strip().lower() for part in (raw or "").split(",") if part.strip()]
    if not values:
        return list(ALL_CAPABILITIES)
    known = set(ALL_CAPABILITIES)
    return [v for v in values if v in known]


@dataclass(slots=True)
class NodeIdentity:
    node_id: str
    name: str
    version: str
    mode: MeshMode
    role: MeshRole
    capabilities: list[str]
    priority: int
    host: str
    port: int


def build_node_identity(
    *,
    seed: str,
    version: str,
    mode: MeshMode,
    capabilities: list[str],
    priority: int = 0,
    name: str = "",
    host: str = "",
    port: int = 0,
    role: MeshRole | None = None,
) -> NodeIdentity:
    """Assemble this node's identity.

    In standalone mode the role is always STANDALONE; in a mesh it starts as
    WORKER and the election promotes one node to COORDINATOR.
    """
    effective_role = (
        MeshRole.STANDALONE if mode is MeshMode.STANDALONE else role or MeshRole.WORKER
    )
    return NodeIdentity(
        node_id=derive_node_id(seed),
        name=(name or default_node_name()).strip()[:120],
        version=version,
        mode=mode,
        role=effective_role,
        capabilities=list(capabilities),
        priority=int(priority),
        host=host,
        port=int(port),
    )


__all__ = [
    "NODE_ID_PREFIX",
    "NodeIdentity",
    "build_node_identity",
    "default_node_name",
    "derive_node_id",
    "parse_mode",
    "resolve_capabilities",
]
