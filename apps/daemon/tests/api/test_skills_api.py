from fastapi import FastAPI
from httpx import AsyncClient

from thoth_daemon.schemas import SkillDefinition
from thoth_daemon.storage.skills import SkillStore


async def test_skills_seeded_with_builtins(client: AsyncClient) -> None:
    # Built-in skills are seeded idempotently.
    r = await client.get("/api/skills")
    assert r.status_code == 200
    names = {s["name"] for s in r.json()}
    assert {
        "continue-project",
        "project-health-check",
        "research-and-save",
        "prepare-git-commit",
        "organize-workspace",
        "run-project-tests",
    } <= names


async def test_skills_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/skills", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


async def test_patch_toggles_and_persists(client: AsyncClient, app: FastAPI) -> None:
    store: SkillStore = app.state.skills
    sk = SkillDefinition(
        name="demo", description="d", workflow=["fs_stat"], inputs=[], enabled=True
    )
    await store.add_skill(sk)

    listed = (await client.get("/api/skills")).json()
    mine = next(s for s in listed if s["id"] == sk.id)
    assert mine["enabled"] is True

    r = await client.patch(f"/api/skills/{sk.id}", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    listed = (await client.get("/api/skills")).json()
    assert next(s for s in listed if s["id"] == sk.id)["enabled"] is False


async def test_patch_unknown_404(client: AsyncClient) -> None:
    r = await client.patch("/api/skills/nope", json={"enabled": False})
    assert r.status_code == 404


async def test_patch_extra_field_422(client: AsyncClient, app: FastAPI) -> None:
    store: SkillStore = app.state.skills
    sk = SkillDefinition(name="d2", description="d", workflow=[], inputs=[], enabled=True)
    await store.add_skill(sk)
    r = await client.patch(f"/api/skills/{sk.id}", json={"enabled": False, "x": 1})
    assert r.status_code == 422
