"""Append-only audit store.

Deliberately exposes NO update/delete/clear surface (a test enforces this).
Each event gets a per-task monotonic ``seq`` assigned under an async lock so
ordering is deterministic and independent of wall-clock resolution
(ADR-007). Payloads are redacted before they touch the database.
"""

import asyncio
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from thoth_daemon.schemas import AuditEvent
from thoth_daemon.security.redaction import redact
from thoth_daemon.storage.models import AuditEventRow


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
            seq = await self._next_seq(session, task_id)
            event = AuditEvent(
                correlation_id=correlation_id,
                task_id=task_id,
                seq=seq,
                event_type=event_type,
                payload=redact(payload, extra_fields=redaction_fields),
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
                )
            )
            await session.commit()
            return event

    async def for_task(self, task_id: str) -> list[AuditEvent]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(AuditEventRow)
                        .where(AuditEventRow.task_id == task_id)
                        .order_by(AuditEventRow.seq)
                    )
                )
                .scalars()
                .all()
            )
            return [self._to_event(row) for row in rows]

    async def _next_seq(self, session: AsyncSession, task_id: str) -> int:
        rows = (
            await session.execute(
                select(AuditEventRow.seq)
                .where(AuditEventRow.task_id == task_id)
                .order_by(AuditEventRow.seq.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return 0 if rows is None else rows + 1

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
        )
