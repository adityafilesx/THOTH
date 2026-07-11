from httpx import AsyncClient


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
