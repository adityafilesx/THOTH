"""Skill engine (Phase 4 slice 5).

A skill is a DECLARATIVE, parameterized plan template. Running one
produces an ExecutionPlan that flows through the NORMAL pipeline
(validation → policy risk review → approvals → scoped execution →
independent verification → bounded recovery). The engine is planning-only
— it never executes tools — and can never lower a risk level or remove
verification.
"""

from pathlib import Path

import pytest

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.approvals import ApprovalEngine
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.planner import DeterministicMockPlanner
from thoth_daemon.core.policy import PolicyEngine
from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.core.skill_engine import SkillEngine, SkillInputError, seed_builtin_skills
from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.schemas import (
    RiskLevel,
    SkillDefinition,
    SkillStep,
    TaskState,
    WorkspaceProfile,
)
from thoth_daemon.storage.db import init_schema, make_engine, make_session_factory
from thoth_daemon.storage.skills import SkillStore
from thoth_daemon.tools.mock_tools import build_registry


def _skill(**overrides) -> SkillDefinition:
    base = dict(
        name="demo",
        description="demo skill",
        inputs=["project_path"],
        workflow=["read the file"],
        steps=[
            SkillStep(
                title="Read {project_path}",
                tool_name="mock_read_file",
                arguments={"path": "{project_path}/README.md"},
                declared_risk=RiskLevel.R0,
            )
        ],
    )
    base.update(overrides)
    return SkillDefinition.model_validate(base)


engine = SkillEngine()


class TestExpansion:
    def test_substitutes_placeholders_everywhere(self) -> None:
        plan = engine.expand(_skill(), {"project_path": "/tmp/proj"}, task_id="t1")
        assert plan.task_id == "t1"
        assert plan.steps[0].arguments == {"path": "/tmp/proj/README.md"}
        assert plan.steps[0].title == "Read /tmp/proj"
        assert plan.steps[0].index == 0

    def test_unknown_placeholder_rejected(self) -> None:
        skill = _skill(
            steps=[
                SkillStep(
                    title="x",
                    tool_name="mock_read_file",
                    arguments={"path": "{mystery}/f"},
                    declared_risk=RiskLevel.R0,
                )
            ]
        )
        with pytest.raises(SkillInputError, match="mystery"):
            engine.expand(skill, {"project_path": "/p"}, task_id="t1")

    def test_missing_input_rejected(self) -> None:
        with pytest.raises(SkillInputError, match="project_path"):
            engine.expand(_skill(), {}, task_id="t1")

    def test_extra_input_rejected(self) -> None:
        with pytest.raises(SkillInputError, match="sneaky"):
            engine.expand(_skill(), {"project_path": "/p", "sneaky": "x"}, task_id="t1")

    def test_declared_risks_copied_verbatim_never_lowered(self) -> None:
        skill = _skill(
            inputs=[],
            steps=[
                SkillStep(
                    title="send",
                    tool_name="mock_send_email",
                    arguments={"recipient": "a@b.c", "subject": "s", "body": "b"},
                    declared_risk=RiskLevel.R2,
                )
            ],
        )
        plan = engine.expand(skill, {}, task_id="t1")
        assert plan.steps[0].declared_risk is RiskLevel.R2

    def test_nested_substitution_in_lists_and_dicts(self) -> None:
        skill = _skill(
            steps=[
                SkillStep(
                    title="x",
                    tool_name="mock_read_file",
                    arguments={"path": "{project_path}", "meta": {"tags": ["{project_path}"]}},
                    declared_risk=RiskLevel.R0,
                )
            ]
        )
        plan = engine.expand(skill, {"project_path": "/p"}, task_id="t1")
        assert plan.steps[0].arguments["meta"] == {"tags": ["/p"]}


class TestPipelineIntegration:
    async def _orch(self, tmp_path: Path) -> Orchestrator:
        db = make_engine(tmp_path / "s.db")
        await init_schema(db)

        async def publish(_t: str, _p: dict) -> None:
            return None

        return Orchestrator(
            registry=build_registry(),
            policy=PolicyEngine(),
            approvals=ApprovalEngine(ttl_seconds=60),
            verifier=VerificationEngine(),
            recovery=RecoveryController(),
            audit=AuditStore(make_session_factory(db)),
            planner=DeterministicMockPlanner(),
            publish=publish,
            workspace=WorkspaceProfile(name="w", root_path="/ws", trusted=True),
        )

    async def test_skill_task_flows_through_normal_pipeline(self, tmp_path: Path) -> None:
        orch = await self._orch(tmp_path)
        plan = engine.expand(_skill(), {"project_path": "/p"}, task_id="ignored")
        task = await orch.submit_plan("run skill demo", plan)
        settled = await orch.settle(task.id)
        assert settled.state is TaskState.COMPLETED
        events = await orch.task_audit(task.id)
        assert "policy.decision" in [e.event_type for e in events]  # risk review ran

    async def test_skill_cannot_bypass_approval_with_lowered_risk(self, tmp_path: Path) -> None:
        """A skill declaring R0 for a tool whose default is R2 still halts
        for approval: effective risk = max(tool default, declared)."""
        orch = await self._orch(tmp_path)
        skill = _skill(
            inputs=[],
            steps=[
                SkillStep(
                    title="sneaky send",
                    tool_name="mock_send_email",
                    arguments={"recipient": "a@b.c", "subject": "s", "body": "b"},
                    declared_risk=RiskLevel.R0,  # attempted downgrade
                )
            ],
        )
        plan = engine.expand(skill, {}, task_id="ignored")
        task = await orch.submit_plan("sneaky", plan)
        settled = await orch.settle(task.id)
        assert settled.state is TaskState.WAITING_FOR_APPROVAL


class TestSeeds:
    async def test_seed_builtin_skills_idempotent(self, tmp_path: Path) -> None:
        db = make_engine(tmp_path / "seeds.db")
        await init_schema(db)
        store = SkillStore(make_session_factory(db))
        created = await seed_builtin_skills(store)
        assert len(created) == 5
        again = await seed_builtin_skills(store)
        assert again == []  # idempotent
        names = {s.name for s in await store.list_skills()}
        assert names == {
            "continue-project",
            "project-health-check",
            "research-and-save",
            "prepare-git-commit",
            "organize-workspace",
        }

    async def test_seeded_skills_expand_cleanly(self, tmp_path: Path) -> None:
        db = make_engine(tmp_path / "seeds2.db")
        await init_schema(db)
        store = SkillStore(make_session_factory(db))
        await seed_builtin_skills(store)
        inputs = {
            "continue-project": {"project_path": "/p"},
            "project-health-check": {"project_path": "/p"},
            "research-and-save": {"url": "https://example.com", "dest_path": "/p/out.md"},
            "prepare-git-commit": {"repo_path": "/p"},
            "organize-workspace": {"workspace_path": "/p"},
        }
        for skill in await store.list_skills():
            plan = engine.expand(skill, inputs[skill.name], task_id="t")
            assert plan.steps, skill.name
            assert [s.index for s in plan.steps] == list(range(len(plan.steps)))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
