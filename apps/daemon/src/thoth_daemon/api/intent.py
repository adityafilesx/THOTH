"""Intent classification endpoint (Phase 5 slice 3).

Classification-ONLY: given a text (typed or transcribed), return which tier
would handle it (reflex / skill / planner) and the resolved reflex action
or planner goal. It does NOT execute the intent or invoke any inference
provider — the reflex/skill tiers are provably LLM-free, and running the
planner is deferred to the normal task pipeline. Reflex-action execution
wiring (stop/cancel/run-skill/continue-workspace) lands with the
interaction surfaces and workspace profiles.
"""

from time import perf_counter
from typing import Any, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.core.intent_router import (
    IntentRouter,
    ReflexKind,
    RouteTier,
    build_skill_aliases,
)
from thoth_daemon.storage.skills import SkillStore
from thoth_daemon.voice.metrics import VoiceLatencyMetrics, VoiceLatencyStage

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
    return IntentRouter(
        known_apps=_BASE_APPS,
        known_skills=names,
        known_workspaces={"THOTH"},
        skill_aliases=build_skill_aliases(names),
    )


@router.post("/api/intent/route")
async def route_intent(body: RouteBody, request: Request) -> dict[str, Any]:
    intent_router = await _build_router(request)
    started = perf_counter()
    routed = intent_router.route(body.text)
    elapsed_ms = (perf_counter() - started) * 1_000
    metrics = cast(VoiceLatencyMetrics, request.app.state.voice_metrics)
    if routed.tier is RouteTier.REFLEX:
        stage = (
            VoiceLatencyStage.SKILL_ROUTE
            if routed.reflex_kind is ReflexKind.RUN_SKILL
            else VoiceLatencyStage.REFLEX_ROUTE
        )
        metrics.record(stage, elapsed_ms)
    return routed.model_dump(mode="json")
