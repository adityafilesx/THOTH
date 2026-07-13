from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.skill_engine import SkillEngine, SkillInputError
from thoth_daemon.security.redaction import redact
from thoth_daemon.storage.skills import SkillStore

router = APIRouter()
SYSTEM_TASK_ID = "system"


class SkillPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


def _skills(request: Request) -> SkillStore:
    return cast(SkillStore, request.app.state.skills)


@router.get("/api/skills")
async def list_skills(request: Request) -> list[dict[str, Any]]:
    return [s.model_dump(mode="json") for s in await _skills(request).list_skills()]


@router.patch("/api/skills/{skill_id}")
async def patch_skill(skill_id: str, body: SkillPatch, request: Request) -> dict[str, Any]:
    updated = await _skills(request).set_enabled(skill_id, body.enabled)
    if updated is None:
        raise HTTPException(status_code=404, detail="skill not found")
    audit = cast(AuditStore, request.app.state.audit)
    await audit.append(
        SYSTEM_TASK_ID, "skill.toggled", {"skill_id": skill_id, "enabled": body.enabled}
    )
    return updated.model_dump(mode="json")


class SkillRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str] = {}


@router.post("/api/skills/{skill_id}/run")
async def run_skill(skill_id: str, body: SkillRunBody, request: Request) -> dict[str, Any]:
    """Expand a skill into a plan and run it through the NORMAL pipeline
    (policy review, approvals, scoped execution, independent verification,
    bounded recovery). Planning-only expansion — the engine executes nothing."""
    skill = await _skills(request).get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="skill not found")
    if not skill.enabled:
        raise HTTPException(status_code=409, detail="skill is disabled")
    engine = SkillEngine()
    try:
        plan = engine.expand(skill, body.inputs, task_id="pending")
    except SkillInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit = cast(AuditStore, request.app.state.audit)
    await audit.append(
        SYSTEM_TASK_ID,
        "skill.run_requested",
        {"skill": skill.name, "inputs": redact(body.inputs)},
    )
    orch = cast(Orchestrator, request.app.state.orchestrator)
    task = await orch.submit_plan(f"Run skill: {skill.name}", plan)
    settled = await orch.settle(task.id)
    return settled.model_dump(mode="json")
