from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from thoth_daemon.app import create_app
from thoth_daemon.config import Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "test.db",
        log_dir=tmp_path / "logs",
        trusted_workspaces=[str(tmp_path / "trusted")],
        approval_ttl_seconds=60,
        session_token="test-token",
        session_token_path=tmp_path / "session.token",
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
