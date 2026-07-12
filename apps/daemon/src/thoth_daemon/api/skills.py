from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.audit.store import AuditStore
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
