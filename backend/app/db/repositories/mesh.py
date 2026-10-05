"""Repositories for LAN Mesh nodes, peers, pairing codes and leases (v1.3)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models.mesh import (
    LeaseStatus,
    MeshLease,
    MeshNode,
    MeshPeer,
    PairingCode,
)


class MeshNodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, node: MeshNode) -> MeshNode:
        self.session.add(node)
        await self.session.flush()
        return node

    async def get(self, node_id: str) -> MeshNode | None:
        return await self.session.get(MeshNode, node_id)

    async def get_by_node_id(self, node_id: str) -> MeshNode | None:
        stmt = select(MeshNode).where(MeshNode.node_id == node_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def get_self(self) -> MeshNode | None:
        """Return this computer's node row (the single most recent one)."""
        stmt = select(MeshNode).order_by(MeshNode.created_at)
        return (await self.session.execute(stmt)).scalars().first()


class MeshPeerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, peer: MeshPeer) -> MeshPeer:
        self.session.add(peer)
        await self.session.flush()
        return peer

    async def get(self, peer_id: str) -> MeshPeer | None:
        return await self.session.get(MeshPeer, peer_id)

    async def get_by_node_id(self, node_id: str) -> MeshPeer | None:
        stmt = select(MeshPeer).where(MeshPeer.node_id == node_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def list_all(self, *, trusted: bool | None = None) -> list[MeshPeer]:
        stmt = select(MeshPeer)
        if trusted is not None:
            stmt = stmt.where(MeshPeer.trusted == trusted)
        stmt = stmt.order_by(MeshPeer.name, MeshPeer.node_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, peer: MeshPeer) -> None:
        await self.session.delete(peer)
        await self.session.flush()


class PairingCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, code: PairingCode) -> PairingCode:
        self.session.add(code)
        await self.session.flush()
        return code

    async def get(self, code_id: str) -> PairingCode | None:
        return await self.session.get(PairingCode, code_id)

    async def find_active(self, code: str, *, now: datetime) -> PairingCode | None:
        stmt = (
            select(PairingCode)
            .where(PairingCode.code == code, PairingCode.used.is_(False))
            .order_by(PairingCode.created_at.desc())
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return None
        if row.expires_at is not None:
            # SQLite returns naive datetimes; compare on a common awareness.
            expires = row.expires_at
            if expires.tzinfo is None and now.tzinfo is not None:
                expires = expires.replace(tzinfo=now.tzinfo)
            elif expires.tzinfo is not None and now.tzinfo is None:
                now = now.replace(tzinfo=expires.tzinfo)
            if expires < now:
                return None
        return row


class MeshLeaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, lease: MeshLease) -> MeshLease:
        self.session.add(lease)
        await self.session.flush()
        return lease

    async def get(self, lease_id: str) -> MeshLease | None:
        return await self.session.get(MeshLease, lease_id)

    async def active_for_job(self, job_id: str) -> MeshLease | None:
        stmt = (
            select(MeshLease)
            .where(MeshLease.job_id == job_id, MeshLease.status == LeaseStatus.ACTIVE)
            .order_by(MeshLease.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def list_all(self, *, limit: int = 200) -> list[MeshLease]:
        stmt = select(MeshLease).order_by(MeshLease.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_active(self) -> list[MeshLease]:
        stmt = select(MeshLease).where(MeshLease.status == LeaseStatus.ACTIVE)
        return list((await self.session.execute(stmt)).scalars().all())


__all__ = [
    "MeshLeaseRepository",
    "MeshNodeRepository",
    "MeshPeerRepository",
    "PairingCodeRepository",
]
