from httpx import AsyncClient


class TestTaskEndpoints:
    async def test_create_r0_task_completes(self, client: AsyncClient) -> None:
        resp = await client.post("/api/tasks", json={"goal": "read my notes"})
        assert resp.status_code == 200
        task = resp.json()
        assert task["state"] == "COMPLETED"
        assert task["plan"]["steps"]

    async def test_create_task_rejects_extra_fields(self, client: AsyncClient) -> None:
        resp = await client.post("/api/tasks", json={"goal": "x", "sneaky": 1})
        assert resp.status_code == 422

    async def test_list_and_get_task(self, client: AsyncClient) -> None:
        created = (await client.post("/api/tasks", json={"goal": "read notes"})).json()
        listing = (await client.get("/api/tasks")).json()
        assert any(t["id"] == created["id"] for t in listing)
        fetched = (await client.get(f"/api/tasks/{created['id']}")).json()
        assert fetched["id"] == created["id"]

    async def test_get_missing_task_404(self, client: AsyncClient) -> None:
        assert (await client.get("/api/tasks/nope")).status_code == 404

    async def test_audit_endpoint_returns_ordered_events(self, client: AsyncClient) -> None:
        task = (await client.post("/api/tasks", json={"goal": "read notes"})).json()
        audit = (await client.get(f"/api/tasks/{task['id']}/audit")).json()
        seqs = [e["seq"] for e in audit]
        assert seqs == list(range(len(seqs)))
        assert audit[0]["event_type"] == "task.created"

    async def test_audit_verify_endpoint_returns_valid_manifest(self, client: AsyncClient) -> None:
        task = (await client.post("/api/tasks", json={"goal": "read notes"})).json()
        manifest = (await client.get(f"/api/tasks/{task['id']}/audit/verify")).json()
        assert manifest["valid"] is True
        assert manifest["events"] > 0
        assert len(manifest["head_hash"]) == 64
        assert manifest["first_invalid_seq"] is None


class TestApprovalEndpoints:
    async def test_r2_halts_and_can_be_approved(self, client: AsyncClient) -> None:
        task = (await client.post("/api/tasks", json={"goal": "send the email"})).json()
        assert task["state"] == "WAITING_FOR_APPROVAL"

        pending = (await client.get("/api/approvals/pending")).json()
        assert len(pending) == 1

        final = (
            await client.post(
                f"/api/approvals/{pending[0]['id']}/decision", json={"approved": True}
            )
        ).json()
        assert final["state"] == "COMPLETED"

    async def test_r2_deny_fails_task(self, client: AsyncClient) -> None:
        await client.post("/api/tasks", json={"goal": "send the email"})
        pending = (await client.get("/api/approvals/pending")).json()
        final = (
            await client.post(
                f"/api/approvals/{pending[0]['id']}/decision", json={"approved": False}
            )
        ).json()
        assert final["state"] == "FAILED"

    async def test_r3_task_fails(self, client: AsyncClient) -> None:
        task = (await client.post("/api/tasks", json={"goal": "delete the build directory"})).json()
        assert task["state"] == "FAILED"

    async def test_cancel_waiting_task(self, client: AsyncClient) -> None:
        task = (await client.post("/api/tasks", json={"goal": "send the email"})).json()
        cancelled = (await client.post(f"/api/tasks/{task['id']}/cancel")).json()
        assert cancelled["state"] == "CANCELLED"
