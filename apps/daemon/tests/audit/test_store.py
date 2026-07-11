from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = make_engine(tmp_path / "audit.db")
    await init_schema(engine)
    yield make_session_factory(engine)
    await engine.dispose()


async def test_append_assigns_monotonic_sequence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    for i in range(5):
        await store.append("task-1", "state.transition", {"i": i})
    events = await store.for_task("task-1")
    assert [e.seq for e in events] == [0, 1, 2, 3, 4]


async def test_sequences_are_independent_per_task(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    await store.append("task-a", "x", {})
    await store.append("task-b", "x", {})
    await store.append("task-a", "y", {})
    assert [e.seq for e in await store.for_task("task-a")] == [0, 1]
    assert [e.seq for e in await store.for_task("task-b")] == [0]


async def test_events_ordered_by_sequence(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    types = ["a", "b", "c", "d"]
    for t in types:
        await store.append("task-1", t, {})
    events = await store.for_task("task-1")
    assert [e.event_type for e in events] == types


async def test_secret_payload_is_redacted_at_rest(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    await store.append("task-1", "tool.result", {"api_key": "sk-live-123", "recipient": "a@b.c"})
    event = (await store.for_task("task-1"))[0]
    assert event.payload["api_key"] == "[REDACTED]"
    assert event.payload["recipient"] == "a@b.c"


async def test_extra_redaction_fields_applied(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AuditStore(session_factory)
    await store.append(
        "task-1",
        "tool.result",
        {"recipient": "a@b.c", "body": "secret"},
        redaction_fields=["recipient", "body"],
    )
    event = (await store.for_task("task-1"))[0]
    assert event.payload["recipient"] == "[REDACTED]"
    assert event.payload["body"] == "[REDACTED]"


async def test_store_exposes_no_mutation_api(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Append-only: the store must not offer update or delete methods."""
    store = AuditStore(session_factory)
    public = {name for name in dir(store) if not name.startswith("_")}
    assert not (public & {"update", "delete", "remove", "clear", "edit"})
