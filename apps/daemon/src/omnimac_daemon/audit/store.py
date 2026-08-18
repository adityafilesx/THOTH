"""Append-only audit store.

Deliberately exposes NO update/delete/clear surface (a test enforces this).
Each event gets a per-task monotonic ``seq`` assigned under an async lock so
ordering is deterministic and independent of wall-clock resolution
(ADR-007). Payloads are redacted before they touch the database.

Slice 9: every event extends a per-task tamper-evident hash chain
(``audit/chain.py``); ``verify_chain`` recomputes it and reports the first
break, catching direct-database tampering done around this store.
"""

import asyncio
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from omnimac_daemon.audit.chain import ChainManifest, compute_event_hash
from omnimac_daemon.schemas import AuditEvent
from omnimac_daemon.security.redaction import redact
from omnimac_daemon.storage.models import AuditEventRow


class AuditStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def append(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        redaction_fields: list[str] | None = None,
        correlation_id: str = "",
    ) -> AuditEvent:
        async with self._locks[task_id], self._session_factory() as session:
            seq, prev_hash = await self._chain_head(session, task_id)
            event = AuditEvent(
                correlation_id=correlation_id,
                task_id=task_id,
                seq=seq,
                event_type=event_type,
                payload=redact(payload, extra_fields=redaction_fields),
                prev_hash=prev_hash,
            )
            event.hash = compute_event_hash(
                prev_hash=prev_hash,
                task_id=event.task_id,
                correlation_id=event.correlation_id,
                seq=event.seq,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
            session.add(
                AuditEventRow(
                    event_id=event.event_id,
                    correlation_id=event.correlation_id,
                    task_id=event.task_id,
                    seq=event.seq,
                    event_type=event.event_type,
                    payload_json=event.payload,
                    created_at=event.created_at,
                    prev_hash=event.prev_hash,
                    hash=event.hash,
                )
            )
            await session.commit()
            return event

    async def for_task(self, task_id: str) -> list[AuditEvent]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(AuditEventRow).where(AuditEventRow.task_id == task_id).order_by(AuditEventRow.seq))).scalars().all()
            return [self._to_event(row) for row in rows]

    async def verify_chain(self, task_id: str) -> ChainManifest:
        """Recompute the task's hash chain from genesis and compare against
        the stored hashes. Any mutation, deletion (seq gap), or reorder
        yields ``valid=False`` with the first offending sequence."""
        events = await self.for_task(task_id)
        prev_hash = ""
        for index, event in enumerate(events):
            if event.seq != index:
                return ChainManifest(
                    task_id=task_id,
                    valid=False,
                    events=len(events),
                    head_hash=events[-1].hash if events else "",
                    first_invalid_seq=index,
                    reason=f"sequence gap: expected seq {index}, found {event.seq}",
                )
            expected = compute_event_hash(
                prev_hash=prev_hash,
                task_id=event.task_id,
                correlation_id=event.correlation_id,
                seq=event.seq,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
            if event.prev_hash != prev_hash or event.hash != expected:
                return ChainManifest(
                    task_id=task_id,
                    valid=False,
                    events=len(events),
                    head_hash=events[-1].hash,
                    first_invalid_seq=event.seq,
                    reason="stored hash does not match recomputation",
                )
            prev_hash = event.hash
        return ChainManifest(
            task_id=task_id,
            valid=True,
            events=len(events),
            head_hash=prev_hash,
        )

    async def _chain_head(self, session: AsyncSession, task_id: str) -> tuple[int, str]:
        """Next seq and the hash of the latest event (chain tail)."""
        row = (
            await session.execute(
                select(AuditEventRow.seq, AuditEventRow.hash).where(AuditEventRow.task_id == task_id).order_by(AuditEventRow.seq.desc()).limit(1)
            )
        ).first()
        if row is None:
            return 0, ""
        return row[0] + 1, row[1] or ""

    @staticmethod
    def _to_event(row: AuditEventRow) -> AuditEvent:
        return AuditEvent(
            event_id=row.event_id,
            correlation_id=row.correlation_id or "",
            task_id=row.task_id,
            seq=row.seq,
            event_type=row.event_type,
            payload=row.payload_json,
            created_at=row.created_at,
            prev_hash=row.prev_hash or "",
            hash=row.hash or "",
        )
