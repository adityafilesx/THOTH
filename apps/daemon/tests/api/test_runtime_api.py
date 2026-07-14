from fastapi import FastAPI
from httpx import AsyncClient


async def test_runtime_status_exposes_local_components(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    response = await client.get("/api/runtime")
    assert response.status_code == 200
    body = response.json()
    assert body["offline"] is False
    assert body["reflex_available"] is True
    assert set(body["components"]) == {"planner", "speech_recognition", "text_to_speech"}
    assert body["components"]["speech_recognition"]["state"] in {
        "unloaded",
        "degraded",
        "failed",
    }
    assert "api_key" not in response.text.lower()
    assert body["voice_latency"] == {"stages": {}}


async def test_runtime_exposes_bounded_live_voice_latency(client: AsyncClient) -> None:
    routed = await client.post("/api/intent/route", json={"text": "Thoth, stop."})
    assert routed.status_code == 200

    body = (await client.get("/api/runtime")).json()
    reflex = body["voice_latency"]["stages"]["reflex_route"]
    assert reflex["count"] == 1
    assert reflex["p50_ms"] >= 0
    assert reflex["p95_ms"] >= reflex["p50_ms"]
