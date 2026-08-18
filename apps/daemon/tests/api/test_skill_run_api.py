"""POST /api/skills/{id}/run (Phase 4 slice 5).

Runs a skill through the live app: expansion -> policy review -> scoped
execution -> verification. Uses the seeded built-in skills plus a custom
mock-tool skill injected through the store.
"""

from httpx import AsyncClient


async def _skill_id(client: AsyncClient, name: str) -> str:
    skills = (await client.get("/api/skills")).json()
    return next(s["id"] for s in skills if s["name"] == name)


class TestSkillRun:
    async def test_builtin_skills_are_seeded(self, client: AsyncClient) -> None:
        names = {s["name"] for s in (await client.get("/api/skills")).json()}
        assert {
            "continue-project",
            "project-health-check",
            "research-and-save",
            "prepare-git-commit",
            "organize-workspace",
        } <= names

    async def test_unknown_skill_404(self, client: AsyncClient) -> None:
        resp = await client.post("/api/skills/nope/run", json={"inputs": {}})
        assert resp.status_code == 404

    async def test_disabled_skill_409(self, client: AsyncClient) -> None:
        sid = await _skill_id(client, "organize-workspace")
        await client.patch(f"/api/skills/{sid}", json={"enabled": False})
        resp = await client.post(f"/api/skills/{sid}/run", json={"inputs": {"workspace_path": "/x"}})
        assert resp.status_code == 409

    async def test_bad_inputs_422(self, client: AsyncClient) -> None:
        sid = await _skill_id(client, "organize-workspace")
        resp = await client.post(f"/api/skills/{sid}/run", json={"inputs": {"wrong": "x"}})
        assert resp.status_code == 422

    async def test_run_flows_through_normal_pipeline(self, client: AsyncClient, settings) -> None:
        """organize-workspace against the trusted workspace: R0 reads
        complete; audit shows policy decisions (risk review ran)."""
        import pathlib

        ws = pathlib.Path(settings.trusted_workspaces[0])
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "a.txt").write_text("x")

        sid = await _skill_id(client, "organize-workspace")
        resp = await client.post(f"/api/skills/{sid}/run", json={"inputs": {"workspace_path": str(ws)}})
        assert resp.status_code == 200
        task = resp.json()
        assert task["state"] == "COMPLETED"
        assert task["plan"]["summary"] == "Skill: organize-workspace"
        audit = (await client.get(f"/api/tasks/{task['id']}/audit")).json()
        types = [e["event_type"] for e in audit]
        assert "policy.decision" in types
        assert types[0] == "task.created"
