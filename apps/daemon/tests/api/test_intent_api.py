"""Intent classification endpoint (Phase 5 slice 3).

Classification only — proves tiering over the live daemon without
executing anything or calling a model.
"""

from httpx import AsyncClient


class TestIntentRoute:
    async def test_reflex_stop(self, client: AsyncClient) -> None:
        r = await client.post("/api/intent/route", json={"text": "Thoth, stop."})
        assert r.status_code == 200
        body = r.json()
        assert body["tier"] == "reflex"
        assert body["reflex_kind"] == "stop"

    async def test_reflex_run_seeded_skill(self, client: AsyncClient) -> None:
        # The five built-in skills are seeded; "run <name>" is a reflex.
        r = await client.post("/api/intent/route", json={"text": "run organize-workspace"})
        body = r.json()
        assert body["tier"] == "reflex"
        assert body["reflex_kind"] == "run_skill"
        assert body["target"] == "organize-workspace"

    async def test_reflex_open_known_app(self, client: AsyncClient) -> None:
        r = await client.post("/api/intent/route", json={"text": "open Finder"})
        body = r.json()
        assert body["tier"] == "reflex"
        assert body["reflex_kind"] == "open_app"
        assert body["target"] == "Finder"

    async def test_novel_request_routes_to_planner(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/intent/route",
            json={"text": "compare last week's commits and write a summary"},
        )
        body = r.json()
        assert body["tier"] == "planner"
        assert body["planner_goal"]

    async def test_requires_auth(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/intent/route",
            json={"text": "stop"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 401
