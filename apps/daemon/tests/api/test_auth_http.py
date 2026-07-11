from httpx import AsyncClient


async def test_health_is_open_without_token(client: AsyncClient) -> None:
    # Health must not require auth — prove it by sending an explicitly bad header.
    r = await client.get("/api/health", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 200


async def test_protected_route_rejects_missing_token(client: AsyncClient) -> None:
    r = await client.get("/api/tasks", headers={"Authorization": ""})
    assert r.status_code == 401


async def test_protected_route_rejects_wrong_token(client: AsyncClient) -> None:
    r = await client.get("/api/tasks", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


async def test_protected_route_accepts_valid_token(client: AsyncClient) -> None:
    # The client fixture attaches the valid bearer by default.
    r = await client.get("/api/tasks")
    assert r.status_code == 200
