"""Real planner behind the frozen PlannerAdapter (Phase 3 slice 8).

Per ADR-019: THOTH's planner must NEVER execute tools (invariant 1), so it does
NOT use the tool-executing claude-agent-sdk agent loop. It makes a single
planning-only call to Claude (Anthropic Messages API, structured JSON output)
that returns a typed ExecutionPlan over the real tool catalog. The plan is model
output — untrusted — and is validated against the ExecutionPlan schema, the tool
registry, the policy engine, and the scope enforcer (all unchanged) before any
risk review or execution. The planner itself performs zero tool execution."""

from __future__ import annotations

import json
from typing import Any, Protocol

from thoth_daemon.core.planner import PlannerAdapter
from thoth_daemon.schemas import ExecutionPlan, PlanStep, RiskLevel
from thoth_daemon.tools.registry import ToolRegistry

MODEL = "claude-opus-4-8"

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "steps"],
    "properties": {
        "summary": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "tool_name", "arguments", "declared_risk"],
                "properties": {
                    "title": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "arguments": {"type": "object"},
                    "declared_risk": {"type": "string", "enum": ["R0", "R1", "R2", "R3"]},
                },
            },
        },
    },
}


def build_system_prompt(registry: ToolRegistry) -> str:
    """A catalog of the real tools + hard rules. The model may plan ONLY over
    these; every choice is still gated downstream by policy + scope + approvals."""
    lines = [
        "You are THOTH's planner. Produce a minimal JSON execution plan that a "
        "deterministic safety engine will review and execute. You never execute "
        "anything yourself.",
        "",
        "Available tools (use ONLY these; never invent a tool or an argument name):",
    ]
    for tool in registry.all():
        lines.append(f"- {tool.name} (default risk {tool.default_risk.value}): {tool.description}")
    lines += [
        "",
        "Rules:",
        "- Use only the tools listed above, with their real argument names.",
        "- Set declared_risk from the tool's stated default risk (never lower it).",
        "- Keep the plan as short as possible; do not add speculative steps.",
        "- Do not attempt destructive, credential-touching, or out-of-scope actions.",
        "- Output must match the provided JSON schema exactly.",
    ]
    return "\n".join(lines)


class PlannerClient(Protocol):
    """Returns a parsed JSON plan dict matching PLAN_SCHEMA. Injected so the
    planner logic is unit-tested without a network call or an API key."""

    def complete_plan(self, system: str, goal: str, schema: dict[str, Any]) -> dict[str, Any]: ...


class AnthropicPlannerClient:
    """Real client: a single structured-output Messages API call. `anthropic` is
    imported lazily so this module loads without the package or an API key."""

    def __init__(self, model: str = MODEL) -> None:
        self._model = model

    def complete_plan(self, system: str, goal: str, schema: dict[str, Any]) -> dict[str, Any]:
        import anthropic

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        resp = client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": f"Goal: {goal}\nProduce the execution plan."}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        parsed: dict[str, Any] = json.loads(text)
        return parsed


class ClaudePlanner(PlannerAdapter):
    """Planning-only planner. Calls the client, maps the result to an
    ExecutionPlan, and returns it — it never touches the tool executor."""

    def __init__(self, registry: ToolRegistry, client: PlannerClient) -> None:
        self._registry = registry
        self._client = client

    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        raw = self._client.complete_plan(build_system_prompt(self._registry), goal, PLAN_SCHEMA)
        raw_steps = raw.get("steps") or []
        if not raw_steps:
            raise ValueError("planner returned no steps")
        steps: list[PlanStep] = []
        for index, step in enumerate(raw_steps):
            steps.append(
                PlanStep(
                    index=index,  # authoritative — not model-supplied
                    title=str(step["title"]),
                    tool_name=str(step["tool_name"]),
                    arguments=dict(step.get("arguments") or {}),
                    declared_risk=RiskLevel(str(step["declared_risk"])),
                )
            )
        return ExecutionPlan(
            task_id=task_id,
            summary=str(raw.get("summary") or f"Plan for: {goal}"),
            steps=steps,
        )
