"""Orchestrator wiring for bounded recovery (Phase 4 slice 8).

Proves the real loop: verification failure → retries → REPLAN (planner
re-invoked with failure context, new plan re-reviewed by policy) →
success; and when every budget is exhausted the task ends in
FAILED_REQUIRES_USER — never a silent failure, never an unbounded loop.
"""

from pathlib import Path

import pytest

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.orchestrator import MAX_EXECUTIONS_PER_TASK, Orchestrator
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


def _step_probing(path: Path, index: int = 0) -> PlanStep:
    """A mock-read step whose independent FILE_EXISTS probe targets ``path``.
    The mock tool always reports success; verification is what gates."""
    return PlanStep(
        index=index,
        title=f"probe {path.name}",
        tool_name="mock_read_file",
        arguments={"path": "/notes.txt"},
        declared_risk=RiskLevel.R0,
        verification_checks=[
            VerificationCheck(kind=VerifierKind.FILE_EXISTS, params={"path": str(path)})
        ],
    )


class _SequencePlanner(PlannerAdapter):
    """Returns one plan per call; records every goal it receives so tests
    can assert the replan carried failure context."""

    def __init__(self, plans: list[ExecutionPlan]) -> None:
        self._plans = plans
        self.calls: list[str] = []

    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        self.calls.append(goal)
        plan = self._plans[min(len(self.calls) - 1, len(self._plans) - 1)]
        return plan.model_copy(update={"task_id": task_id}, deep=True)


async def _orch(
    tmp_path: Path, planner: PlannerAdapter, recovery: RecoveryController | None = None
) -> Orchestrator:
    engine = make_engine(tmp_path / "r.db")
    await init_schema(engine)

    async def publish(_t: str, _p: dict) -> None:
        return None

    return Orchestrator(
        registry=build_registry(),
        policy=PolicyEngine(),
        approvals=ApprovalEngine(ttl_seconds=60),
        verifier=VerificationEngine(),
        recovery=recovery or RecoveryController(),
        audit=AuditStore(make_session_factory(engine)),
        planner=planner,
        publish=publish,
        workspace=WorkspaceProfile(name="w", root_path="/ws", trusted=True),
    )


async def _settle_terminal(orch: Orchestrator, task_id: str, timeout: float = 10.0):
    return await orch.settle(task_id, timeout=timeout)


async def test_replan_recovers_and_completes(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    present = tmp_path / "present.txt"
    present.write_text("here")
    bad = ExecutionPlan(task_id="x", summary="bad", steps=[_step_probing(missing)])
    good = ExecutionPlan(task_id="x", summary="good", steps=[_step_probing(present)])
    planner = _SequencePlanner([bad, good])
    orch = await _orch(tmp_path, planner)

    task = await orch.submit("do the thing")
    settled = await _settle_terminal(orch, task.id)

    assert settled.state is TaskState.COMPLETED
    assert len(planner.calls) == 2
    assert "RECOVERY" in planner.calls[1]  # replan carries failure context
    events = await orch.task_audit(task.id)
    types = [e.event_type for e in events]
    assert "recovery.replanned" in types
    # The replacement plan went through risk review again.
    assert types.count("policy.decision") >= 2


async def test_authoritative_submit_plan_never_replans_via_model(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    present = tmp_path / "present.txt"
    present.write_text("here")
    authoritative = ExecutionPlan(
        task_id="pending",
        summary="authoritative",
        steps=[_step_probing(missing)],
    )
    planner = _SequencePlanner(
        [ExecutionPlan(task_id="x", summary="model replacement", steps=[_step_probing(present)])]
    )
    recovery = RecoveryController(
        max_retries_per_step=0,
        max_retries_per_task=0,
        max_replans_per_task=2,
    )
    orch = await _orch(tmp_path, planner, recovery)

    task = await orch.submit_plan("authoritative operation", authoritative)
    settled = await _settle_terminal(orch, task.id)

    assert settled.state is TaskState.FAILED_REQUIRES_USER
    assert settled.error == (
        "The requested operation could not be verified after bounded retries. "
        "No completion was claimed."
    )
    assert "model-generated" not in settled.error
    assert planner.calls == []
    events = await orch.task_audit(task.id)
    blocked = [event for event in events if event.event_type == "recovery.replan_blocked"]
    assert len(blocked) == 1
    assert "previous plan failed" in blocked[0].payload["reason"]


async def test_budget_exhaustion_ends_in_failed_requires_user(tmp_path: Path) -> None:
    missing = tmp_path / "never.txt"
    bad = ExecutionPlan(task_id="x", summary="bad", steps=[_step_probing(missing)])
    planner = _SequencePlanner([bad])  # every plan (initial + replans) fails
    orch = await _orch(tmp_path, planner)

    task = await orch.submit("do the thing")
    settled = await _settle_terminal(orch, task.id)

    assert settled.state is TaskState.FAILED_REQUIRES_USER
    assert settled.error
    # initial plan + 2 replans, never more
    assert len(planner.calls) == 3
    events = await orch.task_audit(task.id)
    assert "task.failed_requires_user" in [e.event_type for e in events]


async def test_plan_larger_than_step_cap_is_rejected(tmp_path: Path) -> None:
    present = tmp_path / "p.txt"
    present.write_text("x")
    steps = [_step_probing(present, index=i) for i in range(MAX_EXECUTIONS_PER_TASK + 1)]
    big = ExecutionPlan(task_id="x", summary="too big", steps=steps)
    orch = await _orch(tmp_path, _SequencePlanner([big]))

    task = await orch.submit("do everything at once")
    settled = await _settle_terminal(orch, task.id)

    assert settled.state is TaskState.FAILED
    assert "25" in (settled.error or "")


async def test_execution_cap_escalates_even_with_huge_budgets(tmp_path: Path) -> None:
    missing = tmp_path / "never.txt"
    bad = ExecutionPlan(task_id="x", summary="bad", steps=[_step_probing(missing)])
    generous = RecoveryController(
        max_retries_per_step=1000,
        max_retries_per_task=10_000,
        max_replans_per_task=1000,
        max_recovery_depth=1000,
    )
    orch = await _orch(tmp_path, _SequencePlanner([bad]), recovery=generous)

    task = await orch.submit("do the thing")
    settled = await _settle_terminal(orch, task.id, timeout=30.0)

    assert settled.state is TaskState.FAILED_REQUIRES_USER
    assert "execution budget" in (settled.error or "")


async def test_denial_still_fails_immediately_not_requires_user(tmp_path: Path) -> None:
    """Policy/approval denials keep failing to FAILED — escalation is only
    for exhausted recovery budgets."""
    orch = await _orch(tmp_path, _DenyPlanner())
    task = await orch.submit("delete everything")
    settled = await _settle_terminal(orch, task.id)
    assert settled.state is TaskState.FAILED


class _DenyPlanner(PlannerAdapter):
    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        return ExecutionPlan(
            task_id=task_id,
            summary="R3",
            steps=[
                PlanStep(
                    index=0,
                    title="wipe disk",
                    tool_name="mock_delete_dir",
                    arguments={"path": "/"},
                    declared_risk=RiskLevel.R3,
                )
            ],
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
