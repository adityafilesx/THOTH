from pathlib import Path
from typing import Any

import pytest

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.claude_planner import ClaudePlanner, build_system_prompt
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.scope import ScopeEnforcer
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.schemas import ResourceScope, TaskState, WorkspaceProfile
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.tools.fs_tools import register_fs_tools
from thoth_daemon.tools.mock_tools import build_registry
from thoth_daemon.tools.registry import ToolRegistry


class FakePlannerClient:
    def __init__(self, plan: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self._plan = plan
        self._error = error
        self.calls = 0

    def complete_plan(self, system: str, goal: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.system = system
        if self._error is not None:
            raise self._error
        assert self._plan is not None
        return self._plan


def _registry() -> ToolRegistry:
    reg = build_registry()
    register_fs_tools(reg)
    return reg


def test_build_system_prompt_lists_real_tools() -> None:
    prompt = build_system_prompt(_registry())
    for name in ("mock_read_file", "fs_read_file", "fs_write_file", "fs_stat"):
        assert name in prompt
    assert "use ONLY these" in prompt.lower() or "use only the tools" in prompt.lower()


def test_plan_maps_steps_with_authoritative_indexes() -> None:
    client = FakePlannerClient(
        plan={
            "summary": "read then stat",
            "steps": [
                {
                    "title": "read",
                    "tool_name": "mock_read_file",
                    "arguments": {"path": "~/a"},
                    "declared_risk": "R0",
                },
                {
                    "title": "stat",
                    "tool_name": "fs_stat",
                    "arguments": {"path": "~/a"},
                    "declared_risk": "R0",
                },
            ],
        }
    )
    plan = ClaudePlanner(_registry(), client).plan("t1", "read my file")
    assert plan.summary == "read then stat"
    assert [s.index for s in plan.steps] == [0, 1]
    assert plan.steps[0].tool_name == "mock_read_file"
    assert client.calls == 1


def test_plan_empty_steps_raises() -> None:
    client = FakePlannerClient(plan={"summary": "x", "steps": []})
    with pytest.raises(ValueError):
        ClaudePlanner(_registry(), client).plan("t1", "goal")


def test_plan_invalid_risk_raises() -> None:
    client = FakePlannerClient(
        plan={
            "summary": "x",
            "steps": [
                {"title": "t", "tool_name": "fs_stat", "arguments": {}, "declared_risk": "R9"}
            ],
        }
    )
    with pytest.raises(ValueError):
        ClaudePlanner(_registry(), client).plan("t1", "goal")


async def _orch(tmp_path: Path, planner: Any) -> Orchestrator:
    engine = make_engine(tmp_path / "p.db")
    await init_schema(engine)

    async def publish(event_type: str, payload: dict) -> None:
        return None

    reg = _registry()

    async def provider() -> ResourceScope:
        return ResourceScope(paths=[str(tmp_path)])

    return Orchestrator(
        registry=reg,
        policy=PolicyEngine(),
        approvals=ApprovalEngine(ttl_seconds=60),
        verifier=VerificationEngine(),
        recovery=RecoveryController(),
        audit=AuditStore(make_session_factory(engine)),
        planner=planner,
        publish=publish,
        workspace=WorkspaceProfile(name="w", root_path=str(tmp_path), trusted=True),
        enforcer=ScopeEnforcer(),
        scope_provider=provider,
    )


async def test_untrusted_plan_unknown_tool_is_rejected(tmp_path: Path) -> None:
    client = FakePlannerClient(
        plan={
            "summary": "x",
            "steps": [
                {
                    "title": "evil",
                    "tool_name": "not_a_real_tool",
                    "arguments": {},
                    "declared_risk": "R0",
                }
            ],
        }
    )
    orch = await _orch(tmp_path, ClaudePlanner(_registry(), client))
    task = await orch.submit("do a thing")
    settled = await orch.settle(task.id)
    assert settled.state is TaskState.FAILED
    audit = await orch.task_audit(task.id)
    assert any(
        "unknown tool" in (e.payload.get("reason") or "")
        for e in audit
        if e.event_type == "plan.rejected"
    )


async def test_valid_in_scope_plan_completes_planner_called_once(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hi")
    client = FakePlannerClient(
        plan={
            "summary": "stat the note",
            "steps": [
                {
                    "title": "stat",
                    "tool_name": "fs_stat",
                    "arguments": {"path": str(tmp_path / "note.txt")},
                    "declared_risk": "R0",
                }
            ],
        }
    )
    orch = await _orch(tmp_path, ClaudePlanner(_registry(), client))
    task = await orch.submit("check my note")
    settled = await orch.settle(task.id)
    assert settled.state is TaskState.COMPLETED
    assert client.calls == 1  # the planner ran and produced a real plan...
    # ...and it never executed a tool itself — execution happened only via the
    # orchestrator's EXECUTING gate (proven by COMPLETED + verification).


async def test_planner_that_raises_fails_task_cleanly(tmp_path: Path) -> None:
    client = FakePlannerClient(error=RuntimeError("network down"))
    orch = await _orch(tmp_path, ClaudePlanner(_registry(), client))
    task = await orch.submit("anything")  # planner raises -> FAILED, no runner
    assert task.state is TaskState.FAILED and "planning failed" in (task.error or "")
    assert await orch.settle(task.id) is task
