from pathlib import Path

from pydantic import BaseModel, ConfigDict

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.planner import PlannerAdapter
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.scope import ScopeEnforcer
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.schemas import (
    ExecutionPlan,
    PlanStep,
    ResourceScope,
    RiskLevel,
    TaskState,
    VerificationStrategy,
    WorkspaceProfile,
)
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.tools.base import ToolDefinition
from thoth_daemon.tools.registry import ToolRegistry


class _ProbeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str


class _ProbeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


class _ProbeTool(ToolDefinition[_ProbeIn, _ProbeOut]):
    name = "scoped_probe"
    description = "reads a path"
    input_model = _ProbeIn
    output_model = _ProbeOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def __init__(self) -> None:
        super().__init__()
        self.ran = 0

    def requested_scope(self, args: _ProbeIn) -> ResourceScope:  # type: ignore[override]
        return ResourceScope(paths=[args.path])

    async def run(self, args: _ProbeIn, dry_run: bool) -> _ProbeOut:
        self.ran += 1
        return _ProbeOut(ok=True)


class _OneStepPlanner(PlannerAdapter):
    def __init__(self, path: str) -> None:
        self._path = path

    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        return ExecutionPlan(
            task_id=task_id,
            summary=goal,
            steps=[
                PlanStep(
                    index=0,
                    title="probe",
                    tool_name="scoped_probe",
                    arguments={"path": self._path},
                    declared_risk=RiskLevel.R0,
                )
            ],
        )


async def _build(
    tmp_path: Path, allowed_paths: list[str], requested_path: str
) -> tuple[Orchestrator, _ProbeTool]:
    engine = make_engine(tmp_path / "s.db")
    await init_schema(engine)

    async def publish(event_type: str, payload: dict) -> None:
        return None

    async def provider() -> ResourceScope:
        return ResourceScope(paths=allowed_paths)

    registry = ToolRegistry()
    tool = _ProbeTool()
    registry.register(tool)
    orch = Orchestrator(
        registry=registry,
        policy=PolicyEngine(),
        approvals=ApprovalEngine(ttl_seconds=60),
        verifier=VerificationEngine(),
        recovery=RecoveryController(),
        audit=AuditStore(make_session_factory(engine)),
        planner=_OneStepPlanner(requested_path),
        publish=publish,
        workspace=WorkspaceProfile(name="w", root_path=allowed_paths[0], trusted=True),
        enforcer=ScopeEnforcer(),
        scope_provider=provider,
    )
    return orch, tool


async def test_in_scope_step_completes(tmp_path: Path) -> None:
    root = str(Path.home() / "projects" / "thoth")
    orch, tool = await _build(tmp_path, [root], root + "/a.txt")
    task = await orch.submit("probe")
    settled = await orch.settle(task.id)
    assert settled.state is TaskState.COMPLETED and tool.ran == 1


async def test_out_of_scope_step_fails_before_executing(tmp_path: Path) -> None:
    root = str(Path.home() / "projects" / "thoth")
    orch, tool = await _build(tmp_path, [root], str(Path.home() / "secret" / "a.txt"))
    task = await orch.submit("probe")
    settled = await orch.settle(task.id)
    assert settled.state is TaskState.FAILED
    assert tool.ran == 0
    audit = await orch.task_audit(task.id)
    types = [e.event_type for e in audit]
    assert "scope.denied" in types
    assert not any(
        e.event_type == "state.transition" and e.payload.get("to") == "EXECUTING" for e in audit
    )
    assert not any(e.event_type == "tool.result" for e in audit)
