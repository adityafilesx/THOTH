"""Capstone workflow harness (Phase 4 slice 10).

Runs a natural-language goal through the FULL pipeline — plan → registry
validation → policy risk review → approval (real single-use
ApprovalEngine, granted programmatically in harness runs and recorded as
such) → real tool execution in EXECUTING → in-loop verification → bounded
recovery — and then INDEPENDENTLY re-verifies the final world state with
the real probes from core/verifiers.

Planner selection:
- ``scripted``: each capstone carries a reference plan (harness proof —
  proves everything downstream of planning against the real OS).
- ``claude``: the live planner turns the same natural-language goal into
  the plan. PENDING LIVE VERIFICATION — requires ANTHROPIC_API_KEY.

Reports never contain step arguments (tool names, risks, and check
outcomes only).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.planner import PlannerAdapter
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.core.verifiers import VerifierContext, evaluate_check
from thoth_daemon.schemas import (
    ExecutionPlan,
    PlanStep,
    ResourceScope,
    RiskLevel,
    TaskState,
    ToolResult,
    VerificationCheck,
    VerifierKind,
    WorkspaceProfile,
)
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.tools.app_tools import register_app_tools
from thoth_daemon.tools.browser_tools import register_browser_tools
from thoth_daemon.tools.fs_tools import register_fs_tools
from thoth_daemon.tools.git_tools import register_git_tools
from thoth_daemon.tools.registry import ToolRegistry
from thoth_daemon.tools.shell_tool import register_shell_tool

WORKSPACE_TOKEN = "{workspace}"


class CapstoneWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    goal: str
    reference_steps: list[PlanStep]
    final_checks: list[VerificationCheck] = Field(min_length=1)
    approved_domains: list[str] = Field(default_factory=list)
    approved_apps: list[str] = Field(default_factory=list)
    needs: str = ""  # environment note (network, TCC, ...)


class CheckOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    passed: bool
    detail: str


class CapstoneResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capstone: str
    planner: str
    task_state: str
    approvals_granted: int
    check_results: list[CheckOutcome]
    final_state_verified: bool
    detail: str = ""


class _ScriptedPlanner(PlannerAdapter):
    """Harness-proof planner: returns the capstone's reference plan. NOT
    the live planner — clearly recorded in the report."""

    def __init__(self, steps: list[PlanStep], summary: str) -> None:
        self._steps = steps
        self._summary = summary

    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        steps = [step.model_copy(deep=True) for step in self._steps]
        return ExecutionPlan(task_id=task_id, summary=self._summary, steps=steps)


def _bind(value: Any, workspace: Path) -> Any:
    if isinstance(value, str):
        return value.replace(WORKSPACE_TOKEN, str(workspace))
    if isinstance(value, dict):
        return {k: _bind(v, workspace) for k, v in value.items()}
    if isinstance(value, list):
        return [_bind(item, workspace) for item in value]
    return value


def _bound_capstone(capstone: CapstoneWorkflow, workspace: Path) -> CapstoneWorkflow:
    return CapstoneWorkflow.model_validate(_bind(capstone.model_dump(), workspace))


def _final_context() -> VerifierContext:
    """Real probes + the no-TCC application probe (NSWorkspace listing)."""
    ctx = VerifierContext.with_real_probes()
    try:
        from thoth_daemon.macos.app_control import default_app_control

        control = default_app_control()
        ctx.application_running = lambda name: any(a.name == name for a in control.list_running())
    except Exception:  # pragma: no cover - non-mac environments
        pass
    return ctx


async def run_capstone(
    capstone: CapstoneWorkflow,
    workspace: Path,
    planner: Literal["scripted", "claude"] = "scripted",
    db_dir: Path | None = None,
) -> CapstoneResult:
    capstone = _bound_capstone(capstone, workspace)

    registry = ToolRegistry()
    register_fs_tools(registry)
    register_shell_tool(registry)
    register_git_tools(registry)
    register_app_tools(registry)
    register_browser_tools(registry)

    planner_impl: PlannerAdapter
    if planner == "scripted":
        planner_impl = _ScriptedPlanner(capstone.reference_steps, f"Capstone: {capstone.name}")
    else:
        import os

        if not os.environ.get("ANTHROPIC_API_KEY"):
            return CapstoneResult(
                capstone=capstone.name,
                planner="claude",
                task_state="NOT_RUN",
                approvals_granted=0,
                check_results=[],
                final_state_verified=False,
                detail="pending live verification: ANTHROPIC_API_KEY not set",
            )
        from thoth_daemon.core.claude_planner import AnthropicPlannerClient, ClaudePlanner

        planner_impl = ClaudePlanner(registry, AnthropicPlannerClient())

    # The audit DB must live OUTSIDE the workspace: the final GIT_STATE
    # probe verifies the world the task acted on, and the harness must not
    # pollute it.
    engine = make_engine((db_dir or workspace.parent) / f"capstone-{capstone.name}.db")
    await init_schema(engine)

    async def publish(_t: str, _p: dict[str, Any]) -> None:
        return None

    scope = ResourceScope(
        paths=[str(workspace)],
        domains=capstone.approved_domains,
        apps=capstone.approved_apps,
    )

    async def scope_provider() -> ResourceScope:
        return scope

    orch = Orchestrator(
        registry=registry,
        policy=PolicyEngine(),
        approvals=ApprovalEngine(ttl_seconds=120),
        verifier=VerificationEngine(),
        recovery=RecoveryController(),
        audit=AuditStore(make_session_factory(engine)),
        planner=planner_impl,
        publish=publish,
        workspace=WorkspaceProfile(name="capstone", root_path=str(workspace), trusted=True),
        scope_provider=scope_provider,
    )

    task = await orch.submit(capstone.goal)
    approvals_granted = 0
    for _ in range(20):  # bounded approval loop
        settled = await orch.settle(task.id, timeout=30.0)
        if settled.state is not TaskState.WAITING_FOR_APPROVAL:
            break
        pending = orch.pending_approvals()
        if not pending:
            await asyncio.sleep(0.05)
            continue
        # Harness-granted approval through the REAL single-use engine;
        # recorded so the report shows the human step was simulated.
        await orch.decide_approval(pending[0].id, approved=True)
        approvals_granted += 1
    settled = await orch.settle(task.id, timeout=30.0)

    ctx = _final_context()
    probe_result = ToolResult(invocation_id="capstone-final", ok=True)
    outcomes = [
        CheckOutcome(
            kind=check.kind.value,
            passed=(o := evaluate_check(check, ctx, probe_result)).passed and o.available,
            detail=o.detail,
        )
        for check in capstone.final_checks
    ]
    verified = settled.state is TaskState.COMPLETED and all(o.passed for o in outcomes)
    await engine.dispose()
    return CapstoneResult(
        capstone=capstone.name,
        planner=planner,
        task_state=settled.state.value,
        approvals_granted=approvals_granted,
        check_results=outcomes,
        final_state_verified=verified,
        detail=settled.error or "",
    )


def render_capstone_report(results: list[CapstoneResult], planner: str) -> str:
    lines = [
        "# Capstone report — Phase 4 slice 10",
        "",
        f"Planner: `{planner}`.",
        "",
        "Scripted runs prove the full pipeline downstream of planning against "
        "the REAL OS (policy review, single-use approvals, scoped execution, "
        "in-loop verification, bounded recovery, independent final-state "
        "probes). Natural-language planning through the live Claude planner is "
        "**pending live verification** (requires ANTHROPIC_API_KEY). Harness "
        "approvals are granted programmatically through the real approval "
        "engine and recorded below.",
        "",
        "| capstone | task state | approvals | final state verified | checks |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        checks = (
            ", ".join(f"{c.kind}:{'ok' if c.passed else 'FAIL'}" for c in r.check_results) or "—"
        )
        lines.append(
            f"| {r.capstone} | {r.task_state} | {r.approvals_granted} | "
            f"{'YES' if r.final_state_verified else 'no'} | {checks} |"
        )
    lines.append("")
    for r in results:
        if r.detail:
            lines.append(f"- `{r.capstone}`: {r.detail}")
    lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------- definitions

CAPSTONES: list[CapstoneWorkflow] = [
    CapstoneWorkflow(
        name="create-project-note",
        goal=f"Create a note file at {WORKSPACE_TOKEN}/idea.txt saying 'phase four capstone'",
        reference_steps=[
            PlanStep(
                index=0,
                title="Write the note",
                tool_name="fs_write_file",
                arguments={
                    "path": f"{WORKSPACE_TOKEN}/idea.txt",
                    "content": "phase four capstone",
                },
                declared_risk=RiskLevel.R1,
            )
        ],
        final_checks=[
            VerificationCheck(
                kind=VerifierKind.FILE_EXISTS, params={"path": f"{WORKSPACE_TOKEN}/idea.txt"}
            ),
            VerificationCheck(
                kind=VerifierKind.FILE_CONTENT,
                params={
                    "path": f"{WORKSPACE_TOKEN}/idea.txt",
                    "contains": "phase four capstone",
                },
            ),
        ],
    ),
    CapstoneWorkflow(
        name="continue-project",
        goal=f"Re-orient in the project at {WORKSPACE_TOKEN}: listing, git state, README",
        reference_steps=[
            PlanStep(
                index=0,
                title="List the project",
                tool_name="fs_list_dir",
                arguments={"path": WORKSPACE_TOKEN},
                declared_risk=RiskLevel.R0,
            ),
            PlanStep(
                index=1,
                title="Git status",
                tool_name="git_status",
                arguments={"cwd": WORKSPACE_TOKEN},
                declared_risk=RiskLevel.R0,
            ),
            PlanStep(
                index=2,
                title="Read the README",
                tool_name="fs_read_file",
                arguments={"path": f"{WORKSPACE_TOKEN}/README.md"},
                declared_risk=RiskLevel.R0,
            ),
        ],
        final_checks=[
            VerificationCheck(
                kind=VerifierKind.GIT_STATE,
                params={"repo": WORKSPACE_TOKEN, "branch": "main", "clean": True},
            ),
            VerificationCheck(
                kind=VerifierKind.FILE_EXISTS, params={"path": f"{WORKSPACE_TOKEN}/README.md"}
            ),
        ],
    ),
    CapstoneWorkflow(
        name="research-and-save",
        goal=f"Read https://example.com and save research notes to {WORKSPACE_TOKEN}/research.md",
        approved_domains=["example.com"],
        needs="network egress to example.com",
        reference_steps=[
            PlanStep(
                index=0,
                title="Read the page",
                tool_name="browser_read",
                arguments={"url": "https://example.com"},
                declared_risk=RiskLevel.R1,
            ),
            PlanStep(
                index=1,
                title="Save the research notes",
                tool_name="fs_write_file",
                arguments={
                    "path": f"{WORKSPACE_TOKEN}/research.md",
                    "content": "# Research: example.com\n\nCaptured by THOTH capstone run.",
                },
                declared_risk=RiskLevel.R1,
            ),
        ],
        final_checks=[
            VerificationCheck(
                kind=VerifierKind.FILE_CONTENT,
                params={"path": f"{WORKSPACE_TOKEN}/research.md", "contains": "example.com"},
            ),
        ],
    ),
    CapstoneWorkflow(
        name="prepare-commit",
        goal=f"Record a change in {WORKSPACE_TOKEN} and stage it for my review (no commit)",
        reference_steps=[
            PlanStep(
                index=0,
                title="Write the change",
                tool_name="fs_write_file",
                arguments={
                    "path": f"{WORKSPACE_TOKEN}/CHANGES.txt",
                    "content": "capstone change",
                },
                declared_risk=RiskLevel.R2,  # elevated: exercises the approval flow
            ),
            PlanStep(
                index=1,
                title="Stage the change",
                tool_name="git_add",
                arguments={"cwd": WORKSPACE_TOKEN, "paths": ["CHANGES.txt"]},
                declared_risk=RiskLevel.R1,
            ),
        ],
        final_checks=[
            VerificationCheck(
                kind=VerifierKind.GIT_STATE, params={"repo": WORKSPACE_TOKEN, "clean": False}
            ),
            VerificationCheck(
                kind=VerifierKind.FILE_EXISTS, params={"path": f"{WORKSPACE_TOKEN}/CHANGES.txt"}
            ),
        ],
    ),
    CapstoneWorkflow(
        name="launch-app",
        goal="Open the TextEdit application",
        approved_apps=["TextEdit"],
        needs="macOS GUI session (launches TextEdit)",
        reference_steps=[
            PlanStep(
                index=0,
                title="Launch TextEdit",
                tool_name="app_launch",
                arguments={"app": "TextEdit"},
                declared_risk=RiskLevel.R1,
            )
        ],
        final_checks=[
            VerificationCheck(kind=VerifierKind.APPLICATION_RUNNING, params={"name": "TextEdit"}),
        ],
    ),
]
