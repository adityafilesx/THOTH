"""Focus policy is enforced around the authoritative execution path."""

from pathlib import Path

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
from thoth_daemon.tools.base import ToolDefinition
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

    def __init__(self, control: MockAppControl, policy: FocusPolicy) -> None:
        super().__init__()
        self._control = control
        self.focus_policy = policy
        self.runs = 0

    def focus_target(self, args: _In) -> str:
        return args.app

    async def run(self, args: _In, dry_run: bool) -> _Out:
        self.runs += 1
        self._control.set_frontmost(
            AppInfo(name=args.app, bundle_id=f"com.test.{args.app}", active=True)
        )
        return _Out(ran=True)


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
    tmp_path: Path, policy: FocusPolicy
) -> tuple[Orchestrator, _FocusTool, dict[str, FocusRestorationResult]]:
    engine = make_engine(tmp_path / f"focus-{policy.value}.db")
    await init_schema(engine)
    control = MockAppControl([AppInfo(name="Finder", bundle_id="com.apple.finder", active=True)])
    tool = _FocusTool(control, policy)
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
    )


async def test_background_focus_theft_is_detected_and_audited(tmp_path: Path) -> None:
    orch, tool, results = await _orchestrator(tmp_path, FocusPolicy.DO_NOT_STEAL_FOCUS)
    task = await orch.submit("run background probe")
    settled = await orch.settle(task.id)

    assert settled.state is TaskState.COMPLETED
    assert tool.runs == 1
    assert results[task.id].verified is False
    assert results[task.id].detail == "focus was stolen unexpectedly"
    audit = await orch.task_audit(task.id)
    assert any(event.event_type == "focus.result" for event in audit)


async def test_ambiguous_focus_executes_nothing(tmp_path: Path) -> None:
    orch, tool, results = await _orchestrator(tmp_path, FocusPolicy.ASK_IF_AMBIGUOUS)
    task = await orch.submit("ambiguous focus probe")
    settled = await orch.settle(task.id)

    assert settled.state is TaskState.FAILED_REQUIRES_USER
    assert tool.runs == 0
    assert results[task.id].requires_user is True
