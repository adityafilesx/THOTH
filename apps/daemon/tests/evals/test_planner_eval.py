"""Planner evaluation framework (Phase 4 slice 1).

The harness scores any PlannerAdapter against declarative expectations
(allowed tools, step caps, risk ceilings) and writes a REDACTED report:
step arguments are excluded by construction, so no secret or personal
value can leak into docs/evaluations. Proven offline against the
deterministic mock planner; the live Claude run is pending an API key.
"""

from pathlib import Path

import pytest

from omnimac_daemon.core.planner import DeterministicMockPlanner, PlannerAdapter
from omnimac_daemon.evals.planner_eval import (
    MOCK_CASES,
    EvalCase,
    EvalExpectation,
    evaluate_plan,
    render_report_markdown,
    run_planner_evals,
    write_report,
)
from omnimac_daemon.schemas import ExecutionPlan, PlanStep, RiskLevel


def _plan(*steps: tuple[str, RiskLevel]) -> ExecutionPlan:
    return ExecutionPlan(
        task_id="t1",
        summary="test plan",
        steps=[
            PlanStep(
                index=i,
                title=f"step {i}",
                tool_name=tool,
                arguments={"path": "/secret-arg-value.txt"},
                declared_risk=risk,
            )
            for i, (tool, risk) in enumerate(steps)
        ],
    )


def case(**expect) -> EvalCase:
    return EvalCase(name="c", goal="do the thing", expect=EvalExpectation(**expect))


class TestEvaluatePlan:
    def test_pass_within_expectations(self) -> None:
        plan = _plan(("mock_read_file", RiskLevel.R0))
        result = evaluate_plan(case(allowed_tools=["mock_read_file"], max_steps=3, max_risk=RiskLevel.R1), plan)
        assert result.passed and result.failures == []

    def test_disallowed_tool_fails(self) -> None:
        plan = _plan(("mock_git_push", RiskLevel.R2))
        result = evaluate_plan(case(allowed_tools=["mock_read_file"]), plan)
        assert not result.passed
        assert any("mock_git_push" in f for f in result.failures)

    def test_step_cap_fails(self) -> None:
        plan = _plan(("mock_read_file", RiskLevel.R0), ("mock_read_file", RiskLevel.R0))
        result = evaluate_plan(case(max_steps=1), plan)
        assert not result.passed

    def test_risk_ceiling_fails(self) -> None:
        plan = _plan(("mock_send_email", RiskLevel.R2))
        result = evaluate_plan(case(max_risk=RiskLevel.R1), plan)
        assert not result.passed
        assert any("R2" in f for f in result.failures)

    def test_must_use_tool_fails_when_absent(self) -> None:
        plan = _plan(("mock_read_file", RiskLevel.R0))
        result = evaluate_plan(case(must_use_tools=["mock_open_app"]), plan)
        assert not result.passed


class _ExplodingPlanner(PlannerAdapter):
    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        raise RuntimeError("no api key")


class TestRunEvals:
    def test_mock_planner_suite_produces_report(self) -> None:
        report = run_planner_evals(DeterministicMockPlanner(), MOCK_CASES, planner_name="mock")
        assert report.cases_total == len(MOCK_CASES)
        assert report.cases_passed == report.cases_total  # mock is deterministic
        assert report.pass_rate == 1.0

    def test_planner_exception_is_a_case_failure_not_a_crash(self) -> None:
        report = run_planner_evals(_ExplodingPlanner(), MOCK_CASES[:1], planner_name="boom")
        assert report.cases_passed == 0
        assert "planner raised" in report.results[0].failures[0]

    def test_report_is_redacted_by_construction(self, tmp_path: Path) -> None:
        """Step ARGUMENTS never appear in the report — only tool names and
        risk levels — so secrets in arguments cannot leak."""
        planner = DeterministicMockPlanner()
        report = run_planner_evals(planner, MOCK_CASES, planner_name="mock")
        md = render_report_markdown(report)
        assert "arguments" not in md.lower()
        # A known mock-planner argument value must not leak into the report.
        assert "~/draft.md" not in md
        assert "team@example.com" not in md
        path = write_report(report, tmp_path)
        assert path.exists()
        assert path.suffix == ".md"
        text = path.read_text()
        assert "pass rate" in text.lower()

    def test_report_names_planner_and_counts(self) -> None:
        report = run_planner_evals(DeterministicMockPlanner(), MOCK_CASES, planner_name="mock")
        md = render_report_markdown(report)
        assert "mock" in md
        assert str(report.cases_total) in md


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
