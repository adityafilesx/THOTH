"""Tamper-evident audit hash chain (Phase 4 slice 9).

Every audit event carries ``hash = sha256(prev_hash + task_id +
correlation_id + seq + event_type + canonical(payload) + created_at)``.
The chain is per-task (seq is per-task); genesis prev_hash is "". Any
mutation, deletion, or reordering of stored events breaks recomputation
and is reported by ``verify_chain`` with the first offending sequence.
The store still exposes no update/delete surface — this catches tampering
done AROUND the store (direct DB edits).
"""

import itertools
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from thoth_daemon.audit.chain import compute_event_hash
from thoth_daemon.audit.store import AuditStore
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = make_engine(tmp_path / "chain.db")
    await init_schema(engine)
    yield make_session_factory(engine)
    await engine.dispose()


async def _seed(store: AuditStore, task_id: str = "t1", n: int = 4) -> None:
    for i in range(n):
        await store.append(task_id, "state.transition", {"i": i}, correlation_id="corr-1")


async def test_every_event_is_hashed_and_linked(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    await _seed(store)
    events = await store.for_task("t1")
    assert all(len(e.hash) == 64 for e in events)
    assert events[0].prev_hash == ""
    for prev, cur in itertools.pairwise(events):
        assert cur.prev_hash == prev.hash


async def test_hash_is_deterministic_recompute(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    await _seed(store, n=2)
    events = await store.for_task("t1")
    for event in events:
        assert (
            compute_event_hash(
                prev_hash=event.prev_hash,
                task_id=event.task_id,
                correlation_id=event.correlation_id,
                seq=event.seq,
                event_type=event.event_type,
                payload=event.payload,
                created_at=event.created_at,
            )
            == event.hash
        )


async def test_verify_chain_valid(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = AuditStore(session_factory)
    await _seed(store)
    manifest = await store.verify_chain("t1")
    assert manifest.valid
    assert manifest.events == 4
    assert manifest.head_hash == (await store.for_task("t1"))[-1].hash
    assert manifest.first_invalid_seq is None


async def test_payload_tamper_is_detected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    await _seed(store)
    # Tamper AROUND the store: direct SQL edit of a payload.
    async with session_factory() as session:
        await session.execute(
            text(
                "UPDATE audit_events SET payload_json = '{\"i\": 999}' "
                "WHERE task_id = 't1' AND seq = 2"
            )
        )
        await session.commit()
    manifest = await store.verify_chain("t1")
    assert not manifest.valid
    assert manifest.first_invalid_seq == 2


async def test_deleted_event_is_detected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    await _seed(store)
    async with session_factory() as session:
        await session.execute(text("DELETE FROM audit_events WHERE task_id = 't1' AND seq = 1"))
        await session.commit()
    manifest = await store.verify_chain("t1")
    assert not manifest.valid
    assert manifest.first_invalid_seq == 1  # gap where seq 1 should be


async def test_chains_are_independent_per_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    await _seed(store, task_id="a", n=3)
    await _seed(store, task_id="b", n=3)
    # Tampering task a must not invalidate task b.
    async with session_factory() as session:
        await session.execute(
            text("UPDATE audit_events SET event_type = 'forged' WHERE task_id = 'a' AND seq = 0")
        )
        await session.commit()
    assert not (await store.verify_chain("a")).valid
    assert (await store.verify_chain("b")).valid


async def test_empty_chain_is_valid_and_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    manifest = await store.verify_chain("nope")
    assert manifest.valid
    assert manifest.events == 0
    assert manifest.head_hash == ""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
