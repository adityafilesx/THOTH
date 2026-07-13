"""Focus policy is enforced around the authoritative execution path."""

import asyncio
from pathlib import Path
from threading import Event

from pydantic import BaseModel, ConfigDict

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.focus import FocusManager, FocusPolicy, FocusRestorationResult
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.planner import PlannerAdapter
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.macos.app_control import AppInfo, MockAppControl
from thoth_daemon.schemas import (
    ExecutionPlan,
    PlanStep,
    RiskLevel,
    TaskState,
    VerificationStrategy,
    WorkspaceProfile,
)
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.tools.base import IndependentToolVerification, ToolDefinition
from thoth_daemon.tools.registry import ToolRegistry


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: str


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ran: bool


class _FocusTool(ToolDefinition[_In, _Out]):
    name = "focus_probe"
    description = "test-only focus action"
    input_model = _In
    output_model = _Out
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.OUTPUT_ASSERTION

    def __init__(
        self,
        control: MockAppControl,
        policy: FocusPolicy,
        *,
        allow_execution: bool = True,
        verification_entered: Event | None = None,
        verification_release: Event | None = None,
    ) -> None:
        super().__init__()
        self._control = control
        self.focus_policy = policy
        self.runs = 0
        self.frontmost_during_verification: str | None = None
        self.allow_execution = allow_execution
        self.verification_entered = verification_entered
        self.verification_release = verification_release

    def focus_target(self, args: _In) -> str:
        return args.app

    async def run(self, args: _In, dry_run: bool) -> _Out:
        self.runs += 1
        self._control.set_frontmost(
            AppInfo(name=args.app, bundle_id=f"com.test.{args.app}", active=True)
        )
        return _Out(ran=True)

    def verify_independently(self, args: _In) -> IndependentToolVerification:
        if self.verification_entered is not None:
            self.verification_entered.set()
        if self.verification_release is not None:
            self.verification_release.wait(timeout=2)
        frontmost = self._control.frontmost()
        self.frontmost_during_verification = frontmost.bundle_id if frontmost else None
        return IndependentToolVerification(passed=True, detail="test probe passed")

    def validate_execution_authority(self, args: _In) -> None:
        del args
        if not self.allow_execution:
            raise RuntimeError("test execution authority denied")


class _Plan(PlannerAdapter):
    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        return ExecutionPlan(
            task_id=task_id,
            summary=goal,
            steps=[
                PlanStep(
                    index=0,
                    title="focus probe",
                    tool_name="focus_probe",
                    arguments={"app": "TextEdit"},
                    declared_risk=RiskLevel.R0,
                )
            ],
        )


async def _orchestrator(
    tmp_path: Path,
    policy: FocusPolicy,
    *,
    include_target: bool = False,
    allow_execution: bool = True,
    verification_entered: Event | None = None,
    verification_release: Event | None = None,
) -> tuple[
    Orchestrator,
    _FocusTool,
    dict[str, FocusRestorationResult],
    MockAppControl,
]:
    engine = make_engine(tmp_path / f"focus-{policy.value}.db")
    await init_schema(engine)
    running = [AppInfo(name="Finder", bundle_id="com.apple.finder", active=True)]
    if include_target:
        running.append(AppInfo(name="TextEdit", bundle_id="com.test.TextEdit", active=False))
    control = MockAppControl(running)
    tool = _FocusTool(
        control,
        policy,
        allow_execution=allow_execution,
        verification_entered=verification_entered,
        verification_release=verification_release,
    )
    registry = ToolRegistry()
    registry.register(tool)
    results: dict[str, FocusRestorationResult] = {}

    async def publish(event_type: str, payload: dict) -> None:
        return None

    return (
        Orchestrator(
            registry=registry,
            policy=PolicyEngine(),
            approvals=ApprovalEngine(ttl_seconds=60),
            verifier=VerificationEngine(),
            recovery=RecoveryController(max_retries_per_step=0, max_retries_per_task=0),
            audit=AuditStore(make_session_factory(engine)),
            planner=_Plan(),
            publish=publish,
            workspace=WorkspaceProfile(name="w", root_path="/tmp", trusted=True),
            focus_manager=FocusManager(control),
            focus_result_sink=results.__setitem__,
        ),
        tool,
        results,
        control,
    )


async def test_background_focus_theft_is_detected_and_audited(tmp_path: Path) -> None:
    orch, tool, results, _ = await _orchestrator(tmp_path, FocusPolicy.DO_NOT_STEAL_FOCUS)
    task = await orch.submit("run background probe")
    settled = await orch.settle(task.id)

    assert settled.state is TaskState.COMPLETED
    assert tool.runs == 1
    assert results[task.id].verified is False
    assert results[task.id].detail == "focus was stolen unexpectedly"
    audit = await orch.task_audit(task.id)
    assert any(event.event_type == "focus.result" for event in audit)


async def test_ambiguous_focus_executes_nothing(tmp_path: Path) -> None:
    orch, tool, results, _ = await _orchestrator(tmp_path, FocusPolicy.ASK_IF_AMBIGUOUS)
    task = await orch.submit("ambiguous focus probe")
    settled = await orch.settle(task.id)

    assert settled.state is TaskState.FAILED_REQUIRES_USER
    assert tool.runs == 0
    assert results[task.id].requires_user is True


async def test_ax_style_restore_happens_after_independent_verification(
    tmp_path: Path,
) -> None:
    orch, tool, results, control = await _orchestrator(
        tmp_path,
        FocusPolicy.RESTORE_PREVIOUS_FOCUS,
        include_target=True,
    )
    task = await orch.submit("temporarily operate TextEdit")
    settled = await orch.settle(task.id)

    assert settled.state is TaskState.COMPLETED
    assert tool.frontmost_during_verification == "com.test.TextEdit"
    assert control.frontmost() is not None
    assert control.frontmost().bundle_id == "com.apple.finder"
    assert results[task.id].restored is True
    assert results[task.id].verified is True

    audit = await orch.task_audit(task.id)
    event_types = [event.event_type for event in audit]
    assert event_types.index("focus.snapshot") < event_types.index("focus.validation")
    assert event_types.index("focus.validation") < event_types.index("focus.transition")
    assert event_types.index("tool.result") < event_types.index("tool.independent_verification")
    assert event_types.index("tool.independent_verification") < event_types.index("focus.result")


async def test_execution_authority_failure_occurs_before_temporary_focus(
    tmp_path: Path,
) -> None:
    orch, tool, _, control = await _orchestrator(
        tmp_path,
        FocusPolicy.RESTORE_PREVIOUS_FOCUS,
        include_target=True,
        allow_execution=False,
    )
    task = await orch.submit("operate without authority")
    settled = await orch.settle(task.id)

    assert settled.state is TaskState.FAILED_REQUIRES_USER
    assert tool.runs == 0
    assert control.frontmost() is not None
    assert control.frontmost().bundle_id == "com.apple.finder"
    audit = await orch.task_audit(task.id)
    validation = [event for event in audit if event.event_type == "focus.validation"]
    assert validation and validation[-1].payload["authorized"] is False
    assert not any(event.event_type == "focus.transition" for event in audit)


async def test_cancellation_remains_available_during_independent_verification(
    tmp_path: Path,
) -> None:
    entered = Event()
    release = Event()
    orch, _, results, control = await _orchestrator(
        tmp_path,
        FocusPolicy.RESTORE_PREVIOUS_FOCUS,
        include_target=True,
        verification_entered=entered,
        verification_release=release,
    )
    task = await orch.submit("cancel during verification")
    settling = asyncio.create_task(orch.settle(task.id))
    assert await asyncio.to_thread(entered.wait, 1)

    cancelled = await orch.cancel(task.id)
    release.set()
    await settling

    assert cancelled.state is TaskState.CANCELLED
    assert results[task.id].cancelled is True
    assert control.frontmost() is not None
    assert control.frontmost().bundle_id == "com.test.TextEdit"
    audit = await orch.task_audit(task.id)
    verification_events = [
        event for event in audit if event.event_type == "tool.independent_verification"
    ]
    assert verification_events[-1].payload["cancelled"] is True
