"""Orchestrator wiring for independent verification (Phase 4 slice 7).

Proves the real execution loop honours structured verification checks: a
mock tool that reports success cannot complete a step whose declared
postcondition does not hold in the world. 'Exited 0' is not enough.
"""

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.planner import PlannerAdapter
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.schemas import (
    ExecutionPlan,
    PlanStep,
    RiskLevel,
    TaskState,
    VerificationCheck,
    VerificationStrategy,
    VerifierKind,
    WorkspaceProfile,
)
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.tools.base import IndependentToolVerification, ToolDefinition
from thoth_daemon.tools.mock_tools import build_registry
from thoth_daemon.tools.registry import ToolRegistry


class _CheckPlanner(PlannerAdapter):
    """One R0 read step (the mock tool always 'succeeds') carrying a single
    FILE_EXISTS check against ``target``."""

    def __init__(self, target: Path) -> None:
        self._target = target

    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        step = PlanStep(
            index=0,
            title="inspect workspace",
            tool_name="mock_read_file",
            arguments={"path": "/notes.txt"},
            declared_risk=RiskLevel.R0,
            verification_checks=[
                VerificationCheck(kind=VerifierKind.FILE_EXISTS, params={"path": str(self._target)})
            ],
        )
        return ExecutionPlan(task_id=task_id, summary="check", steps=[step])


async def _orch(
    tmp_path: Path,
    planner: PlannerAdapter,
    registry: ToolRegistry | None = None,
) -> Orchestrator:
    engine = make_engine(tmp_path / "v.db")
    await init_schema(engine)

    async def publish(_t: str, _p: dict) -> None:
        return None

    return Orchestrator(
        registry=registry or build_registry(),
        policy=PolicyEngine(),
        approvals=ApprovalEngine(ttl_seconds=60),
        verifier=VerificationEngine(),
        recovery=RecoveryController(max_retries_per_step=1, max_retries_per_task=3),
        audit=AuditStore(make_session_factory(engine)),
        planner=planner,
        publish=publish,
        workspace=WorkspaceProfile(name="w", root_path="/ws", trusted=True),
    )


async def test_step_fails_when_independent_probe_fails(tmp_path: Path) -> None:
    # Tool succeeds, but the declared file never exists → the step can never
    # verify; bounded recovery (slice 8) retries, replans, then escalates to
    # the user instead of silently failing.
    orch = await _orch(tmp_path, _CheckPlanner(tmp_path / "never.txt"))
    task = await orch.submit("inspect")
    settled = await orch.settle(task.id, timeout=10.0)
    assert settled.state is TaskState.FAILED_REQUIRES_USER
    assert "file_exists" in (settled.error or "")


async def test_step_completes_when_independent_probe_passes(tmp_path: Path) -> None:
    target = tmp_path / "present.txt"
    target.write_text("here")
    orch = await _orch(tmp_path, _CheckPlanner(target))
    task = await orch.submit("inspect")
    settled = await orch.settle(task.id)
    assert settled.state is TaskState.COMPLETED


class _ProbeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ProbeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_returned_success: bool


class _FailingIndependentProbeTool(ToolDefinition[_ProbeIn, _ProbeOut]):
    name = "mock_independent_probe"
    description = "Mock action whose independent world-state probe fails."
    input_model = _ProbeIn
    output_model = _ProbeOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.STATE_PROBE

    async def run(self, args: _ProbeIn, dry_run: bool) -> _ProbeOut:
        return _ProbeOut(action_returned_success=True)

    def verify_independently(self, args: _ProbeIn) -> IndependentToolVerification:
        return IndependentToolVerification(
            passed=False,
            detail="fresh external state did not match",
        )


class _ProbePlanner(PlannerAdapter):
    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        return ExecutionPlan(
            task_id=task_id,
            summary="probe",
            steps=[
                PlanStep(
                    index=0,
                    title="probe",
                    tool_name="mock_independent_probe",
                    arguments={},
                    declared_risk=RiskLevel.R0,
                )
            ],
        )


async def test_registered_tool_probe_blocks_false_action_success(tmp_path: Path) -> None:
    registry = build_registry()
    registry.register(_FailingIndependentProbeTool())
    orch = await _orch(tmp_path, _ProbePlanner(), registry)
    task = await orch.submit("probe")
    settled = await orch.settle(task.id, timeout=10)
    assert settled.state is TaskState.FAILED_REQUIRES_USER
    assert "fresh external state did not match" in (settled.error or "")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
