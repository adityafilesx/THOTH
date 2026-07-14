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


async def test_loopback_desktop_preflight_is_allowed(client: AsyncClient) -> None:
    r = await client.options(
        "/api/runtime",
        headers={
            "Origin": "http://localhost:5188",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5188"
    assert "authorization" in r.headers["access-control-allow-headers"].lower()


async def test_native_tauri_preflight_is_allowed(client: AsyncClient) -> None:
    r = await client.options(
        "/api/runtime",
        headers={
            "Origin": "tauri://localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "tauri://localhost"


async def test_non_loopback_origin_is_not_allowed(client: AsyncClient) -> None:
    r = await client.options(
        "/api/runtime",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert "access-control-allow-origin" not in r.headers


async def test_cors_does_not_bypass_bearer_auth(client: AsyncClient) -> None:
    r = await client.get(
        "/api/runtime",
        headers={"Origin": "http://127.0.0.1:5173", "Authorization": ""},
    )

    assert r.status_code == 401
    assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
