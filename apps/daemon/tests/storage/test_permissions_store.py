from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from omnimac_daemon.schemas import PermissionGrant, WorkspaceProfile
from omnimac_daemon.storage.db import init_schema, make_engine, make_session_factory
from omnimac_daemon.storage.permissions import PermissionStore


@pytest.fixture()
async def store(tmp_path: Path) -> AsyncIterator[PermissionStore]:
    engine = make_engine(tmp_path / "perm.db")
    await init_schema(engine)
    yield PermissionStore(make_session_factory(engine))


async def test_upsert_and_list_workspace(store: PermissionStore) -> None:
    await store.upsert_workspace(WorkspaceProfile(name="default", root_path="~/projects/omnimac", trusted=True))
    listed = await store.list_workspaces()
    assert len(listed) == 1 and listed[0].root_path == "~/projects/omnimac"


async def test_add_list_revoke_grant(store: PermissionStore) -> None:
    g = PermissionGrant(workspace_id="w1", kind="domain", value="example.com")
    await store.add_grant(g)
    assert [x.value for x in await store.list_grants()] == ["example.com"]
    assert await store.revoke_grant(g.id) is True
    assert await store.list_grants() == []
    assert await store.revoke_grant("missing") is False


async def test_effective_scope_unions_workspace_and_grants(store: PermissionStore) -> None:
    await store.upsert_workspace(
        WorkspaceProfile(
            id="w1",
            name="default",
            root_path="~/projects/omnimac",
            trusted=True,
            approved_domains=["docs.python.org"],
            approved_apps=["Safari"],
        )
    )
    await store.add_grant(PermissionGrant(workspace_id="w1", kind="path", value="~/scratch"))
    await store.add_grant(PermissionGrant(workspace_id="w1", kind="domain", value="example.com"))
    revoked = PermissionGrant(workspace_id="w1", kind="app", value="Terminal")
    await store.add_grant(revoked)
    await store.revoke_grant(revoked.id)

    scope = await store.effective_scope("w1")
    assert set(scope.paths) == {"~/projects/omnimac", "~/scratch"}
    assert set(scope.domains) == {"docs.python.org", "example.com"}
    assert scope.apps == ["Safari"]  # revoked Terminal excluded


async def test_grants_persist_across_store_instances(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "persist.db")
    await init_schema(engine)
    sf = make_session_factory(engine)
    await PermissionStore(sf).add_grant(PermissionGrant(workspace_id="w1", kind="path", value="~/x"))
    reopened = await PermissionStore(sf).list_grants()
    assert [g.value for g in reopened] == ["~/x"]
