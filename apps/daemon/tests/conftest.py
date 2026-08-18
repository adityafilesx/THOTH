from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from omnimac_daemon.app import create_app
from omnimac_daemon.config import Settings
from omnimac_daemon.storage import db as storage_db


@pytest.fixture(autouse=True)
async def dispose_test_engines(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Close every per-test SQLite engine before its event loop is torn down."""

    engines: list[AsyncEngine] = []
    create_async_engine = storage_db.create_async_engine

    def tracked_create_async_engine(*args: object, **kwargs: object) -> AsyncEngine:
        engine = create_async_engine(*args, **kwargs)
        engines.append(engine)
        return engine

    monkeypatch.setattr(storage_db, "create_async_engine", tracked_create_async_engine)
    yield
    for engine in reversed(engines):
        await engine.dispose()


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "test.db",
        log_dir=tmp_path / "logs",
        trusted_workspaces=[str(tmp_path / "trusted")],
        approval_ttl_seconds=60,
        session_token="test-token",
        session_token_path=tmp_path / "session.token",
        planner="mock",
        inference_provider="deterministic",
    )


@pytest.fixture()
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # ASGITransport does not run lifespan; use the sync TestClient as a
    # lifespan context so startup/shutdown execute.
    with TestClient(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer test-token"},
        ) as c:
            yield c


@pytest.fixture()
def ws_client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, headers={"Authorization": "Bearer test-token"}) as c:
        yield c
