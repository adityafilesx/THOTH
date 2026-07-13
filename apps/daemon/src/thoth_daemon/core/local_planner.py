"""Local constrained planner + strict plan validator (Phase 5 slice 4).

The local model outputs the SAME validated ExecutionPlan contract as every
other planner. The PlanValidator is a deterministic gate that rejects a
model's plan BEFORE risk review or execution when it:

- is malformed (does not parse into an ExecutionPlan),
- exceeds the configured step limit,
- names an unknown tool,
- carries extra or invalid/missing arguments (per the tool's input model),
- reduces a risk level below the tool's default (a downgrade),
- proposes an effectful step with no way to verify it, or
- targets an unsupported application.

None of this replaces the Phase 4 gates — the accepted plan still flows
through registry validation, policy risk review, scope enforcement,
approvals, execution-only-in-EXECUTING, and independent verification. The
validator is an EARLIER, model-specific rejection layer.

Fallback ladder when local inference fails: matching deterministic skill →
clarification → fail safe. It NEVER switches to a cloud model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from thoth_daemon.core.claude_planner import PLAN_SCHEMA, build_system_prompt
from thoth_daemon.core.planner import PlannerAdapter
from thoth_daemon.schemas import ExecutionPlan, RiskLevel, VerificationStrategy
from thoth_daemon.tools.registry import ToolRegistry

# Hard cap matching the orchestrator's per-task execution budget.
MAX_PLAN_STEPS = 25

# Tools whose 'app' argument must reference a supported application.
_APP_ARG_TOOLS = {"app_launch", "app_focus"}


class PlanRejection(StrEnum):
    MALFORMED = "malformed"
    TOO_MANY_STEPS = "too_many_steps"
    UNKNOWN_TOOL = "unknown_tool"
    BAD_ARGUMENTS = "bad_arguments"
    RISK_DOWNGRADE = "risk_downgrade"
    MISSING_VERIFIER = "missing_verifier"
    UNSUPPORTED_APP = "unsupported_app"


class PlanRejected(Exception):
    def __init__(self, kind: PlanRejection, detail: str) -> None:
        super().__init__(f"{kind.value}: {detail}")
        self.kind = kind
        self.detail = detail


class PlanValidator:
    def __init__(
        self,
        registry: ToolRegistry,
        max_steps: int = MAX_PLAN_STEPS,
        known_apps: set[str] | None = None,
    ) -> None:
        self._registry = registry
        self._max_steps = max_steps
        self._apps = known_apps

    def validate(self, raw: dict[str, Any], task_id: str) -> ExecutionPlan:
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise PlanRejected(PlanRejection.MALFORMED, "plan has no steps")
        # Index is authoritative (assigned here, never model-supplied) so the
        # model cannot forge non-contiguous indexes; other per-step fields are
        # validated as-is.
        normalized = {
            "task_id": task_id,
            "summary": str(raw.get("summary") or f"Plan for: {task_id}"),
            "steps": [
                {**{k: v for k, v in step.items() if k != "index"}, "index": i}
                for i, step in enumerate(raw_steps)
                if isinstance(step, dict)
            ],
        }
        try:
            plan = ExecutionPlan.model_validate(normalized)
        except ValidationError as exc:
            raise PlanRejected(PlanRejection.MALFORMED, str(exc)) from exc

        if len(plan.steps) > self._max_steps:
            raise PlanRejected(
                PlanRejection.TOO_MANY_STEPS,
                f"{len(plan.steps)} steps exceeds the limit of {self._max_steps}",
            )

        for step in plan.steps:
            if not self._registry.has(step.tool_name):
                raise PlanRejected(PlanRejection.UNKNOWN_TOOL, f"no such tool {step.tool_name!r}")
            tool = self._registry.get(step.tool_name)

            try:
                tool.input_model.model_validate(step.arguments)
            except ValidationError as exc:
                raise PlanRejected(PlanRejection.BAD_ARGUMENTS, f"{step.tool_name}: {exc}") from exc

            default = tool.default_risk
            if step.declared_risk.rank < default.rank:
                raise PlanRejected(
                    PlanRejection.RISK_DOWNGRADE,
                    f"{step.tool_name}: declared {step.declared_risk.value} below "
                    f"default {default.value}",
                )

            # An effectful step (R1+) must have a verification path: either a
            # tool strategy that actually probes, or explicit checks.
            effectful = step.declared_risk.rank >= RiskLevel.R1.rank
            has_verifier = tool.verification is not VerificationStrategy.NONE_READONLY or bool(
                step.verification_checks
            )
            if effectful and not has_verifier:
                raise PlanRejected(
                    PlanRejection.MISSING_VERIFIER,
                    f"{step.tool_name}: effectful step ({step.declared_risk.value}) with "
                    "no verifier",
                )

            if step.tool_name in _APP_ARG_TOOLS and self._apps is not None:
                app = step.arguments.get("app")
                if app not in self._apps:
                    raise PlanRejected(
                        PlanRejection.UNSUPPORTED_APP, f"unsupported application {app!r}"
                    )

        return plan


class LocalPlanClient(Protocol):
    """Sync plan completion (mirrors ClaudePlanner's PlannerClient) so the
    planner stays a sync PlannerAdapter. Injected for offline tests; the
    real client talks to the loopback local server."""

    def complete_plan(self, system: str, goal: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class LocalPlanner(PlannerAdapter):
    def __init__(
        self,
        registry: ToolRegistry,
        client: LocalPlanClient,
        known_apps: set[str] | None = None,
        validator: PlanValidator | None = None,
    ) -> None:
        self._registry = registry
        self._client = client
        self._validator = validator or PlanValidator(registry, known_apps=known_apps)

    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        system = build_system_prompt(self._registry)
        raw = self._client.complete_plan(system, goal, PLAN_SCHEMA)
        return self._validator.validate(raw, task_id)


class LocalPlanResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    tier: str  # planner | skill | clarify | failed
    plan: ExecutionPlan | None = None
    skill: str | None = None
    message: str = ""


def plan_with_fallback(
    goal: str,
    planner: LocalPlanner,
    skill_for_goal: Any,  # Callable[[str], str | None]
) -> LocalPlanResult:
    """Try the local planner. On ANY failure (inference down, rejected plan),
    fall back deterministically: matching skill → clarification → fail safe.
    Never routes to a cloud model."""
    try:
        plan = planner.plan("pending", goal)
        return LocalPlanResult(tier="planner", plan=plan)
    except Exception as exc:
        skill = skill_for_goal(goal)
        if skill:
            return LocalPlanResult(
                tier="skill", skill=skill, message=f"local planning failed: {exc}"
            )
        return LocalPlanResult(
            tier="clarify",
            message=(
                "I could not build a safe plan for that locally and no installed "
                "skill matches. Could you rephrase or name a skill?"
            ),
        )
