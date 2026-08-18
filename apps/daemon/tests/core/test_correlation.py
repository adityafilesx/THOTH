from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from omnimac_daemon.audit.store import AuditStore
from omnimac_daemon.core.approvals import ApprovalEngine
from omnimac_daemon.core.orchestrator import Orchestrator
from omnimac_daemon.core.planner import DeterministicMockPlanner
from omnimac_daemon.core.policy import PolicyEngine
from omnimac_daemon.core.recovery import RecoveryController
from omnimac_daemon.core.verification import VerificationEngine
from omnimac_daemon.schemas import TaskState, WorkspaceProfile
from omnimac_daemon.storage.db import init_schema, make_engine, make_session_factory
from omnimac_daemon.tools.mock_tools import build_registry


@pytest.fixture()
async def orch(tmp_path: Path) -> AsyncIterator[Orchestrator]:
    engine = make_engine(tmp_path / "c.db")
    await init_schema(engine)

    async def publish(event_type: str, payload: dict) -> None:
        return None

    yield Orchestrator(
        registry=build_registry(),
        policy=PolicyEngine(),
        approvals=ApprovalEngine(ttl_seconds=60),
        verifier=VerificationEngine(),
        recovery=RecoveryController(),
        audit=AuditStore(make_session_factory(engine)),
        planner=DeterministicMockPlanner(),
        publish=publish,
        workspace=WorkspaceProfile(name="w", root_path="/ws", trusted=True),
    )


async def test_correlation_id_minted_and_threads_audit(orch: Orchestrator) -> None:
    task = await orch.submit("read my notes")
    settled = await orch.settle(task.id)
    assert settled.state is TaskState.COMPLETED
    corr = settled.correlation_id
    assert corr  # minted at submit

    audit = await orch.task_audit(task.id)
    assert audit
    assert all(e.correlation_id == corr for e in audit), [e.correlation_id for e in audit]


async def test_correlation_id_on_plan_and_steps(orch: Orchestrator) -> None:
    task = await orch.submit("read my notes")
    settled = await orch.settle(task.id)
    assert settled.plan is not None
    corr = settled.correlation_id
    assert settled.plan.correlation_id == corr
    assert all(s.correlation_id == corr for s in settled.plan.steps)


async def test_correlation_id_on_approval_flow(orch: Orchestrator) -> None:
    task = await orch.submit("send the email")  # R2 -> approval
    await orch.settle(task.id)
    pending = orch.pending_approvals()
    assert len(pending) == 1
    assert pending[0].correlation_id == (orch.get_task(task.id)).correlation_id
