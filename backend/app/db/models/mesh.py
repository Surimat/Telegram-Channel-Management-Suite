"""LAN Mesh / offline control-plane models (v1.3: no-VPS mode).

The suite can run as **Standalone**, as a **LAN Mesh** node (several of the
owner's computers cooperating inside one local network, with no cloud control
plane), or as a **VPS Worker** (the future PostgreSQL control plane). These
models back the LAN Mesh mode:

* :class:`MeshNode` — this computer's own identity (one row): node id, name,
  capabilities, listening port and role.
* :class:`MeshPeer` — a *trusted* peer discovered on the LAN. Peers are never
  trusted automatically: pairing issues a persistent credential whose hash is
  stored here; the raw credential never touches the database.
* :class:`PairingCode` — a short one-time code the coordinator shows to pair a
  new computer.
* :class:`MeshLease` — a job lease with a monotonically increasing
  ``fencing_token``. A worker whose lease expired cannot commit its old result
  because the token no longer matches.

Live SQLite is **never** shared between computers (no multi-writer SQLite over
Syncthing/network share). Syncthing is only an optional transport for
configuration snapshots, artifacts and backups.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MeshMode(enum.StrEnum):
    """How this installation participates in a mesh."""

    STANDALONE = "standalone"    # one computer, everything local (default)
    LAN_MESH = "lan_mesh"        # several computers in one local network
    VPS_WORKER = "vps_worker"    # a worker of a remote control plane


MODE_TITLES = {
    MeshMode.STANDALONE: "Один компьютер",
    MeshMode.LAN_MESH: "Локальная сеть (LAN Mesh)",
    MeshMode.VPS_WORKER: "Удалённый узел (VPS)",
}


class MeshRole(enum.StrEnum):
    """A node's current role in a LAN Mesh."""

    STANDALONE = "standalone"
    COORDINATOR = "coordinator"  # temporarily holds the working state
    WORKER = "worker"


class PeerStatus(enum.StrEnum):
    """Last observed state of a peer (never a guess)."""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    UNKNOWN = "unknown"


PEER_STATUS_TITLES = {
    PeerStatus.ONLINE: "В сети",
    PeerStatus.OFFLINE: "Не в сети",
    PeerStatus.BUSY: "Занят",
    PeerStatus.UNKNOWN: "Неизвестно",
}

#: Capabilities a node can advertise (worker capability matching).
CAP_TELEGRAM = "telegram"
CAP_MEDIA = "media"
CAP_AI = "ai"
CAP_BACKUP = "backup"
CAP_RSS = "rss"
CAP_WEB = "web"

CAPABILITY_TITLES = {
    CAP_TELEGRAM: "Telegram",
    CAP_MEDIA: "Медиа",
    CAP_AI: "Мини-ИИ",
    CAP_BACKUP: "Резервные копии",
    CAP_RSS: "RSS",
    CAP_WEB: "Веб",
}

ALL_CAPABILITIES = (CAP_TELEGRAM, CAP_MEDIA, CAP_AI, CAP_BACKUP, CAP_RSS, CAP_WEB)


class MeshNode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """This computer's identity inside a mesh (exactly one row is meaningful)."""

    __tablename__ = "mesh_nodes"

    node_id: Mapped[str] = mapped_column(String(64), default="", unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    mode: Mapped[MeshMode] = mapped_column(
        Enum(MeshMode, name="mesh_mode"), default=MeshMode.STANDALONE, nullable=False
    )
    role: Mapped[MeshRole] = mapped_column(
        Enum(MeshRole, name="mesh_role"), default=MeshRole.STANDALONE, nullable=False
    )
    # Advertised capabilities (JSON list of CAP_* values).
    capabilities: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # Deterministic election priority (higher wins); ties break on node_id.
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # The coordinator currently believed active (peer node id, "" if self/none).
    coordinator_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MeshNode {self.name!r} mode={self.mode} role={self.role}>"


class MeshPeer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A trusted peer computer discovered on the LAN."""

    __tablename__ = "mesh_peers"

    node_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    capabilities: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    trusted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # SHA-256 of the pairing credential. The raw credential is never stored.
    credential_hash: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    status: Mapped[PeerStatus] = mapped_column(
        Enum(PeerStatus, name="mesh_peer_status"),
        default=PeerStatus.UNKNOWN,
        index=True,
        nullable=False,
    )
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MeshPeer {self.name!r} trusted={self.trusted} status={self.status}>"


class PairingCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A short one-time pairing code shown by the coordinator."""

    __tablename__ = "mesh_pairing_codes"

    code: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    issued_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<PairingCode used={self.used}>"


class LeaseStatus(enum.StrEnum):
    """Lifecycle of a mesh job lease."""

    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    RELEASED = "released"


class MeshLease(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A lease over one job, owned by exactly one worker at a time.

    ``fencing_token`` increases monotonically per job. A worker commits with the
    token it was granted; a stale token (after failover) is rejected, so the old
    owner can never overwrite a newer result.
    """

    __tablename__ = "mesh_leases"

    job_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    # JSON requirements (e.g. {"capability": "telegram", "account_id": "..."}).
    requirements: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    lease_owner: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fencing_token: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)

    status: Mapped[LeaseStatus] = mapped_column(
        Enum(LeaseStatus, name="mesh_lease_status"),
        default=LeaseStatus.ACTIVE,
        index=True,
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<MeshLease job={self.job_id!r} owner={self.lease_owner!r} "
            f"token={self.fencing_token}>"
        )


__all__ = [
    "ALL_CAPABILITIES",
    "CAPABILITY_TITLES",
    "CAP_AI",
    "CAP_BACKUP",
    "CAP_MEDIA",
    "CAP_RSS",
    "CAP_TELEGRAM",
    "CAP_WEB",
    "MODE_TITLES",
    "PEER_STATUS_TITLES",
    "LeaseStatus",
    "MeshLease",
    "MeshMode",
    "MeshNode",
    "MeshPeer",
    "MeshRole",
    "PairingCode",
    "PeerStatus",
]
