from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert isinstance(body["version"], str) and body["version"]


async def test_health_reports_db_state(client: AsyncClient) -> None:
    body = (await client.get("/api/health")).json()
    # Startup ran migrations/create_all; the tasks table must exist.
    assert body["db"] == "ok"
