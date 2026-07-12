from httpx import AsyncClient


async def test_settings_shape(client: AsyncClient) -> None:
    r = await client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "version",
        "planner",
        "approval_ttl_seconds",
        "max_retries_per_step",
        "max_retries_per_task",
        "trusted_workspaces",
    ):
        assert key in body
    assert "session_token" not in body and "token" not in body


async def test_settings_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/settings", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
