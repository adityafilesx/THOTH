"""Intent classification endpoint (Phase 5 slice 3).

Classification-ONLY: given a text (typed or transcribed), return which tier
would handle it (reflex / skill / planner) and the resolved reflex action
or planner goal. It does NOT execute the intent or invoke any inference
provider — the reflex/skill tiers are provably LLM-free, and running the
planner is deferred to the normal task pipeline. Reflex-action execution
wiring (stop/cancel/run-skill/continue-workspace) lands with the
interaction surfaces and workspace profiles.
"""

from typing import Any, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.core.intent_router import IntentRouter
from thoth_daemon.storage.skills import SkillStore

router = APIRouter()

# A small set of always-available reflex apps; the real approved-app list is
# workspace-scoped (slice 13). Kept conservative here.
_BASE_APPS = {"Finder", "TextEdit", "Terminal", "Safari", "Visual Studio Code"}


class RouteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


async def _build_router(request: Request) -> IntentRouter:
    skills = cast(SkillStore, request.app.state.skills)
    names = {s.name for s in await skills.list_skills()}
    aliases: dict[str, str] = {}
    for name in names:
        aliases[name.replace("-", " ")] = name  # "project health check" -> slug
    return IntentRouter(
        known_apps=_BASE_APPS,
        known_skills=names,
        known_workspaces={"THOTH"},
        skill_aliases=aliases,
    )


@router.post("/api/intent/route")
async def route_intent(body: RouteBody, request: Request) -> dict[str, Any]:
    intent_router = await _build_router(request)
    return intent_router.route(body.text).model_dump(mode="json")
