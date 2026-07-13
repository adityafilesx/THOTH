"""Orchestrator wiring for independent verification (Phase 4 slice 7).

Proves the real execution loop honours structured verification checks: a
mock tool that reports success cannot complete a step whose declared
postcondition does not hold in the world. 'Exited 0' is not enough.
"""

from pathlib import Path

import pytest

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
    VerifierKind,
    WorkspaceProfile,
)
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.tools.mock_tools import build_registry


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


async def _orch(tmp_path: Path, planner: PlannerAdapter) -> Orchestrator:
    engine = make_engine(tmp_path / "v.db")
    await init_schema(engine)

    async def publish(_t: str, _p: dict) -> None:
        return None

    return Orchestrator(
        registry=build_registry(),
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
