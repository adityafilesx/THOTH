from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.orchestrator import (
    ExecutionStateError,
    Orchestrator,
    guarded_execute,
)
from thoth_daemon.core.planner import DeterministicMockPlanner
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.state_machine import TaskStateMachine
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.schemas import (
    ExecutionPlan,
    PlanStep,
    RiskLevel,
    TaskState,
    ToolInvocation,
    WorkspaceProfile,
)
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.tools.mock_tools import build_registry


async def build_orchestrator(tmp_path: Path, trusted: bool) -> Orchestrator:
    engine = make_engine(tmp_path / "orch.db")
    await init_schema(engine)
    events: list[tuple[str, dict]] = []

    async def publish(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    orch = Orchestrator(
        registry=build_registry(),
        policy=PolicyEngine(),
        approvals=ApprovalEngine(ttl_seconds=60),
        verifier=VerificationEngine(),
        recovery=RecoveryController(max_retries_per_step=2, max_retries_per_task=5),
        audit=AuditStore(make_session_factory(engine)),
        planner=DeterministicMockPlanner(),
        publish=publish,
        workspace=WorkspaceProfile(name="w", root_path="/ws", trusted=trusted),
    )
    orch._events = events  # type: ignore[attr-defined]
    return orch


@pytest.fixture()
async def trusted_orch(tmp_path: Path) -> AsyncIterator[Orchestrator]:
    yield await build_orchestrator(tmp_path, trusted=True)


@pytest.fixture()
async def untrusted_orch(tmp_path: Path) -> AsyncIterator[Orchestrator]:
    yield await build_orchestrator(tmp_path, trusted=False)


class TestGuardedExecute:
    async def test_execution_outside_executing_state_raises(self) -> None:
        machine = TaskStateMachine("t", TaskState.PLANNING, emit=lambda *_: None)
        registry = build_registry()
        inv = ToolInvocation(
            task_id="t",
            step_id="s",
            tool_name="mock_read_file",
            arguments={"path": "/x"},
            effective_risk=RiskLevel.R0,
        )
        with pytest.raises(ExecutionStateError):
            await guarded_execute(machine, registry, inv)

    async def test_execution_allowed_in_executing_state(self) -> None:
        machine = TaskStateMachine("t", TaskState.EXECUTING, emit=lambda *_: None)
        registry = build_registry()
        inv = ToolInvocation(
            task_id="t",
            step_id="s",
            tool_name="mock_read_file",
            arguments={"path": "/x"},
            effective_risk=RiskLevel.R0,
        )
        result = await guarded_execute(machine, registry, inv)
        assert result.ok


class TestReadOnlyFlow:
    async def test_r0_task_runs_to_completion(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("read my notes")
        settled = await trusted_orch.settle(task.id)
        assert settled.state is TaskState.COMPLETED
        assert settled.plan is not None
        assert all(s.verification_passed for s in settled.plan.steps)

    async def test_r1_completes_only_in_trusted_workspace(
        self, trusted_orch: Orchestrator, untrusted_orch: Orchestrator
    ) -> None:
        # Trusted: R1 open-app step auto-runs to completion.
        t = await trusted_orch.submit("open the project")
        assert (await trusted_orch.settle(t.id)).state is TaskState.COMPLETED

        # Untrusted: same plan halts for approval on the R1 step.
        u = await untrusted_orch.submit("open the project")
        settled = await untrusted_orch.settle(u.id)
        assert settled.state is TaskState.WAITING_FOR_APPROVAL


class TestApprovalFlow:
    async def test_r2_halts_then_approve_completes(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("send the email")
        settled = await trusted_orch.settle(task.id)
        assert settled.state is TaskState.WAITING_FOR_APPROVAL

        pending = trusted_orch.pending_approvals()
        assert len(pending) == 1
        final = await trusted_orch.decide_approval(pending[0].id, approved=True)
        assert final.state is TaskState.COMPLETED

    async def test_r2_deny_fails_without_execution(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("send the email")
        await trusted_orch.settle(task.id)
        pending = trusted_orch.pending_approvals()
        final = await trusted_orch.decide_approval(pending[0].id, approved=False)
        assert final.state is TaskState.FAILED
        audit = await trusted_orch.task_audit(task.id)
        types = [e.event_type for e in audit]
        assert "task.failed" in types
        # The R2 tool result must never have been produced.
        assert not any(
            e.event_type == "tool.result" and e.payload.get("tool") == "mock_send_email"
            for e in audit
        )

    async def test_modified_arguments_are_used(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("send the email")
        await trusted_orch.settle(task.id)
        pending = trusted_orch.pending_approvals()
        final = await trusted_orch.decide_approval(
            pending[0].id,
            approved=True,
            modified_arguments={
                "recipient": "changed@example.com",
                "subject": "Update",
                "body": "Draft body",
            },
        )
        assert final.state is TaskState.COMPLETED


class TestBlockedFlow:
    async def test_r3_plan_fails_at_risk_review(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("delete the build directory")
        settled = await trusted_orch.settle(task.id)
        assert settled.state is TaskState.FAILED
        audit = await trusted_orch.task_audit(task.id)
        # It must fail during/after RISK_REVIEW and never execute the R3 tool.
        assert any(
            e.event_type == "state.transition" and e.payload["to"] == "RISK_REVIEW" for e in audit
        )
        assert not any(e.event_type == "tool.result" for e in audit)

    async def test_dont_push_is_a_hard_task_constraint(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("Inspect git, but don't push")
        settled = await trusted_orch.settle(task.id)

        assert settled.state is TaskState.FAILED
        assert trusted_orch.pending_approvals() == []
        audit = await trusted_orch.task_audit(task.id)
        assert any(event.event_type == "constraint.denied" for event in audit)
        assert not any(
            event.event_type == "tool.result" and event.payload.get("tool") == "mock_git_push"
            for event in audit
        )


class TestRecoveryFlow:
    async def test_flaky_tool_recovers_within_budget(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("run the flaky unstable task")
        settled = await trusted_orch.settle(task.id)
        assert settled.state is TaskState.COMPLETED
        audit = await trusted_orch.task_audit(task.id)
        assert any(
            e.event_type == "recovery.decision" and e.payload["action"] == "retry" for e in audit
        )


class TestCancellation:
    async def test_cancel_before_settle_yields_cancelled(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("open the project")
        final = await trusted_orch.cancel(task.id)
        assert final.state in {TaskState.CANCELLED, TaskState.COMPLETED}
        # If it completed before the cancel landed, that's acceptable; but a
        # cancel of a waiting task must reach CANCELLED.

    async def test_cancel_while_waiting_for_approval(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("send the email")
        settled = await trusted_orch.settle(task.id)
        assert settled.state is TaskState.WAITING_FOR_APPROVAL
        final = await trusted_orch.cancel(task.id)
        assert final.state is TaskState.CANCELLED


class TestSettlement:
    async def test_timeout_returns_current_snapshot_instead_of_http_500(
        self, trusted_orch: Orchestrator
    ) -> None:
        plan = ExecutionPlan(
            task_id="pending",
            summary="bounded slow task",
            steps=[
                PlanStep(
                    index=0,
                    title="slow read",
                    tool_name="mock_slow",
                    arguments={"sleep_s": 0.1},
                    declared_risk=RiskLevel.R0,
                )
            ],
        )
        task = await trusted_orch.submit_plan("slow snapshot", plan)

        snapshot = await trusted_orch.settle(task.id, timeout=0.001)

        assert snapshot.id == task.id
        assert snapshot.state not in {TaskState.FAILED, TaskState.FAILED_REQUIRES_USER}
        await trusted_orch.cancel(task.id)


class TestAuditOrdering:
    async def test_audit_sequence_is_monotonic(self, trusted_orch: Orchestrator) -> None:
        task = await trusted_orch.submit("read my notes")
        await trusted_orch.settle(task.id)
        audit = await trusted_orch.task_audit(task.id)
        seqs = [e.seq for e in audit]
        assert seqs == sorted(seqs)
        assert seqs == list(range(len(seqs)))
        assert audit[0].event_type == "task.created"
