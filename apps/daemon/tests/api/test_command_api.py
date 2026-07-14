from httpx import AsyncClient


class TestCommandEndpoints:
    async def test_typed_stop_is_model_free_and_creates_no_task(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.post(
            "/api/commands",
            json={"text": "thoth stop", "source": "text"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["route"]["tier"] == "reflex"
        assert body["route"]["reflex_kind"] == "stop"
        assert body["control"] == "stopped"
        assert body["response"]["display"]["text"] == ("Stopped. No external action was taken.")
        assert body["task"] is None
        assert (await client.get("/api/tasks")).json() == []

    async def test_novel_typed_command_returns_task_payload(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/commands",
            json={"text": "read my notes", "source": "text"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["route"]["tier"] == "planner"
        assert body["task"]["state"] == "COMPLETED"
