from pathlib import Path

from fastapi.testclient import TestClient
from httpx import AsyncClient

from thoth_daemon.app import create_app
from thoth_daemon.config import Settings


async def _default_ws(client: AsyncClient) -> dict:
    return (await client.get("/api/permissions")).json()["workspaces"][0]


async def test_permissions_lists_seeded_default_workspace(client: AsyncClient) -> None:
    r = await client.get("/api/permissions")
    assert r.status_code == 200
    body = r.json()
    assert "workspaces" in body and "grants" in body
    assert len(body["workspaces"]) == 1


async def test_create_and_list_grant(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    r = await client.post(
        "/api/permissions/grants",
        json={"workspace_id": ws["id"], "kind": "domain", "value": "example.com"},
    )
    assert r.status_code == 200
    grants = (await client.get("/api/permissions")).json()["grants"]
    assert any(g["value"] == "example.com" for g in grants)


async def test_grant_rejects_extra_field(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    r = await client.post(
        "/api/permissions/grants",
        json={"workspace_id": ws["id"], "kind": "domain", "value": "x", "foo": 1},
    )
    assert r.status_code == 422


async def test_grant_rejects_unknown_kind(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    r = await client.post(
        "/api/permissions/grants",
        json={"workspace_id": ws["id"], "kind": "network", "value": "x"},
    )
    assert r.status_code == 422


async def test_revoke_grant(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    created = (
        await client.post(
            "/api/permissions/grants",
            json={"workspace_id": ws["id"], "kind": "app", "value": "Safari"},
        )
    ).json()
    r = await client.delete(f"/api/permissions/grants/{created['id']}")
    assert r.status_code == 200
    grants = (await client.get("/api/permissions")).json()["grants"]
    assert all(g["id"] != created["id"] for g in grants)


async def test_revoke_unknown_grant_404(client: AsyncClient) -> None:
    r = await client.delete("/api/permissions/grants/does-not-exist")
    assert r.status_code == 404


async def test_grant_emits_system_audit_event(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    await client.post(
        "/api/permissions/grants",
        json={"workspace_id": ws["id"], "kind": "domain", "value": "audited.com"},
    )
    audit = (await client.get("/api/tasks/system/audit")).json()
    assert any(e["event_type"] == "permission.granted" for e in audit)


async def test_explicit_workspace_config_supersedes_stale_empty_default(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "persistent.db"
    common = {
        "db_path": db_path,
        "log_dir": tmp_path / "logs",
        "session_token": "test-token",
        "session_token_path": tmp_path / "session.token",
    }
    with TestClient(create_app(Settings(**common, trusted_workspaces=[]))):
        pass

    trusted = tmp_path / "THOTH"
    trusted.mkdir()
    app = create_app(Settings(**common, trusted_workspaces=[str(trusted)]))
    with TestClient(app):
        selected = app.state.default_workspace
        assert selected.root_path == str(trusted.resolve())
        assert selected.trusted is True
        profiles = await app.state.permissions.list_workspaces()
        # The stale row was preserved rather than silently elevated or overwritten.
        assert any(profile.root_path == "" and not profile.trusted for profile in profiles)
        assert any(profile.id == selected.id and profile.trusted for profile in profiles)
