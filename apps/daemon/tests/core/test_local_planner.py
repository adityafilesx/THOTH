"""Local constrained planner + strict plan validator (Phase 5 slice 4).

The local model must output the existing validated ExecutionPlan
contract. The PlanValidator rejects unknown tools, extra/invalid
arguments, risk reduction, oversized plans, effectful steps with no
verifier, and unsupported apps — BEFORE any risk review or execution.
When local inference fails the fallback ladder is skill → clarify → fail
safe; it NEVER switches to a cloud model.
"""

import pytest

from thoth_daemon.browser.browser_adapter import MockBrowser
from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.core.local_planner import (
    LocalPlanner,
    PlanRejected,
    PlanRejection,
    PlanValidator,
    plan_with_fallback,
)
from thoth_daemon.schemas import RiskLevel
from thoth_daemon.tools.app_tools import register_app_tools
from thoth_daemon.tools.browser_tools import BrowserRead
from thoth_daemon.tools.fs_tools import register_fs_tools
from thoth_daemon.tools.registry import ToolRegistry


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_fs_tools(reg)
    register_app_tools(reg)
    return reg


def _plan(*steps: dict) -> dict:
    return {
        "summary": "s",
        "steps": [{"index": i, "title": f"t{i}", **st} for i, st in enumerate(steps)],
    }


VALIDATOR = PlanValidator(_registry(), known_apps={"TextEdit"})


class TestPlanValidator:
    def test_valid_plan_passes(self) -> None:
        raw = _plan(
            {"tool_name": "fs_read_file", "arguments": {"path": "/x"}, "declared_risk": "R0"}
        )
        plan = VALIDATOR.validate(raw, task_id="t1")
        assert plan.task_id == "t1"
        assert plan.steps[0].tool_name == "fs_read_file"

    def test_unknown_tool_rejected(self) -> None:
        raw = _plan({"tool_name": "launch_missiles", "arguments": {}, "declared_risk": "R0"})
        with pytest.raises(PlanRejected) as exc:
            VALIDATOR.validate(raw, task_id="t1")
        assert exc.value.kind is PlanRejection.UNKNOWN_TOOL

    def test_extra_argument_rejected(self) -> None:
        raw = _plan(
            {
                "tool_name": "fs_read_file",
                "arguments": {"path": "/x", "sudo": True},
                "declared_risk": "R0",
            }
        )
        with pytest.raises(PlanRejected) as exc:
            VALIDATOR.validate(raw, task_id="t1")
        assert exc.value.kind is PlanRejection.BAD_ARGUMENTS

    def test_missing_required_argument_rejected(self) -> None:
        raw = _plan({"tool_name": "fs_read_file", "arguments": {}, "declared_risk": "R0"})
        with pytest.raises(PlanRejected) as exc:
            VALIDATOR.validate(raw, task_id="t1")
        assert exc.value.kind is PlanRejection.BAD_ARGUMENTS

    def test_risk_downgrade_rejected(self) -> None:
        # fs_write_file default is R1; a plan declaring R0 is a downgrade.
        raw = _plan(
            {
                "tool_name": "fs_write_file",
                "arguments": {"path": "/x", "content": "y"},
                "declared_risk": "R0",
            }
        )
        with pytest.raises(PlanRejected) as exc:
            VALIDATOR.validate(raw, task_id="t1")
        assert exc.value.kind is PlanRejection.RISK_DOWNGRADE

    def test_risk_upgrade_is_allowed(self) -> None:
        # Declaring a HIGHER risk than the default is safe (effective = max).
        raw = _plan(
            {
                "tool_name": "fs_read_file",
                "arguments": {"path": "/x"},
                "declared_risk": "R1",
                "verification_checks": [{"kind": "file_exists", "params": {"path": "/x"}}],
            }
        )
        plan = VALIDATOR.validate(raw, task_id="t1")
        assert plan.steps[0].declared_risk is RiskLevel.R1

    def test_effectful_step_without_verifier_rejected(self) -> None:
        # fs_read_file is NONE_READONLY; declared R1 with no checks => an
        # effectful step with no way to verify it. Rejected.
        raw = _plan(
            {"tool_name": "fs_read_file", "arguments": {"path": "/x"}, "declared_risk": "R1"}
        )
        with pytest.raises(PlanRejected) as exc:
            VALIDATOR.validate(raw, task_id="t1")
        assert exc.value.kind is PlanRejection.MISSING_VERIFIER

    def test_oversized_plan_rejected(self) -> None:
        steps = [
            {"tool_name": "fs_read_file", "arguments": {"path": f"/x{i}"}, "declared_risk": "R0"}
            for i in range(26)
        ]
        with pytest.raises(PlanRejected) as exc:
            VALIDATOR.validate(_plan(*steps), task_id="t1")
        assert exc.value.kind is PlanRejection.TOO_MANY_STEPS

    def test_unsupported_app_rejected(self) -> None:
        raw = _plan(
            {"tool_name": "app_launch", "arguments": {"app": "Photoshop"}, "declared_risk": "R1"}
        )
        with pytest.raises(PlanRejected) as exc:
            VALIDATOR.validate(raw, task_id="t1")
        assert exc.value.kind is PlanRejection.UNSUPPORTED_APP

    def test_malformed_plan_rejected(self) -> None:
        with pytest.raises(PlanRejected) as exc:
            VALIDATOR.validate({"summary": "no steps"}, task_id="t1")
        assert exc.value.kind is PlanRejection.MALFORMED

    def test_registered_policy_overrides_model_focus_proposal(self) -> None:
        registry = ToolRegistry()
        registry.register(BrowserRead(MockBrowser()))
        validator = PlanValidator(registry)
        raw = _plan(
            {
                "tool_name": "browser_read",
                "arguments": {"url": "https://example.com"},
                "declared_risk": "R1",
                "focus_policy": "keep_new_focus",
            }
        )

        plan = validator.validate(raw, task_id="t1")

        assert plan.steps[0].focus_policy is FocusPolicy.DO_NOT_STEAL_FOCUS


class _FakeClient:
    def __init__(self, plan: dict) -> None:
        self._plan = plan

    def complete_plan(self, system: str, goal: str, schema: dict) -> dict:
        return self._plan


class _FailingClient:
    def complete_plan(self, system: str, goal: str, schema: dict) -> dict:
        raise RuntimeError("local inference unavailable")


class TestLocalPlanner:
    def test_produces_validated_plan(self) -> None:
        good = _plan(
            {"tool_name": "fs_read_file", "arguments": {"path": "/notes"}, "declared_risk": "R0"}
        )
        planner = LocalPlanner(_registry(), _FakeClient(good), known_apps={"TextEdit"})
        plan = planner.plan("t1", "read my notes")
        assert plan.steps[0].tool_name == "fs_read_file"

    def test_downgrade_plan_is_rejected_not_executed(self) -> None:
        bad = _plan(
            {
                "tool_name": "fs_write_file",
                "arguments": {"path": "/x", "content": "y"},
                "declared_risk": "R0",
            }
        )
        planner = LocalPlanner(_registry(), _FakeClient(bad))
        with pytest.raises(PlanRejected):
            planner.plan("t1", "write a file")


class TestFallbackLadder:
    def test_success_uses_planner_tier(self) -> None:
        good = _plan(
            {"tool_name": "fs_read_file", "arguments": {"path": "/n"}, "declared_risk": "R0"}
        )
        planner = LocalPlanner(_registry(), _FakeClient(good))
        result = plan_with_fallback("read notes", planner, skill_for_goal=lambda g: None)
        assert result.tier == "planner"
        assert result.plan is not None

    def test_failure_falls_back_to_matching_skill(self) -> None:
        planner = LocalPlanner(_registry(), _FailingClient())
        result = plan_with_fallback(
            "run the health check", planner, skill_for_goal=lambda g: "project-health-check"
        )
        assert result.tier == "skill"
        assert result.skill == "project-health-check"

    def test_failure_without_skill_requests_clarification(self) -> None:
        planner = LocalPlanner(_registry(), _FailingClient())
        result = plan_with_fallback("do something vague", planner, skill_for_goal=lambda g: None)
        assert result.tier == "clarify"
        assert result.message

    def test_fallback_never_returns_a_cloud_tier(self) -> None:
        planner = LocalPlanner(_registry(), _FailingClient())
        for skill in (lambda g: "project-health-check", lambda g: None):
            result = plan_with_fallback("x", planner, skill_for_goal=skill)
            assert result.tier in ("planner", "skill", "clarify", "failed")
            assert "cloud" not in result.tier and "anthropic" not in result.tier


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
