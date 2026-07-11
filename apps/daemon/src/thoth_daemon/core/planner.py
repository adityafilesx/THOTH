"""Planner.

The planner NEVER executes tools — it only produces an ExecutionPlan, which
is validated against the schema and the tool registry before risk review.

Phase 2 ships a DeterministicMockPlanner: it maps goal keywords to fixed
plans over mock tools, so tests are deterministic and nothing leaves the
machine. The PlannerAdapter interface is frozen; Phase 3 adds a
claude-agent-sdk implementation behind the same contract.
"""

from abc import ABC, abstractmethod

from thoth_daemon.schemas import ExecutionPlan, PlanStep, RiskLevel


class PlannerAdapter(ABC):
    @abstractmethod
    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        raise NotImplementedError


class DeterministicMockPlanner(PlannerAdapter):
    """Keyword-routed mock planner. MOCK — produces plans over mock tools."""

    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        g = goal.lower()
        steps: list[PlanStep]

        if "delete" in g or "rm " in g or "destroy" in g:
            # Intentionally produces an R3 step so risk review can block it.
            steps = [
                self._step(
                    0,
                    "Delete a directory",
                    "mock_delete_dir",
                    {"path": "~/projects/thoth/build"},
                    RiskLevel.R3,
                ),
            ]
        elif "email" in g or "send" in g:
            steps = [
                self._step(
                    0, "Read the draft", "mock_read_file", {"path": "~/draft.md"}, RiskLevel.R0
                ),
                self._step(
                    1,
                    "Send the email",
                    "mock_send_email",
                    {"recipient": "team@example.com", "subject": "Update", "body": "Draft body"},
                    RiskLevel.R2,
                ),
            ]
        elif "push" in g or "git" in g:
            steps = [
                self._step(
                    0,
                    "Inspect repository",
                    "mock_list_dir",
                    {"path": "~/projects/thoth"},
                    RiskLevel.R0,
                ),
                self._step(
                    1,
                    "Push the branch",
                    "mock_git_push",
                    {"remote": "origin", "branch": "main"},
                    RiskLevel.R2,
                ),
            ]
        elif "flaky" in g or "unstable" in g:
            steps = [
                self._step(
                    0, "Run the unstable task", "mock_flaky", {"fail_times": 1}, RiskLevel.R1
                ),
            ]
        elif "open" in g or "project" in g or "continue" in g:
            steps = [
                self._step(
                    0,
                    "Inspect repository",
                    "mock_list_dir",
                    {"path": "~/projects/thoth"},
                    RiskLevel.R0,
                ),
                self._step(
                    1,
                    "Open the editor",
                    "mock_open_app",
                    {"app": "Visual Studio Code"},
                    RiskLevel.R1,
                ),
                self._step(
                    2,
                    "Read the README",
                    "mock_read_file",
                    {"path": "~/projects/thoth/README.md"},
                    RiskLevel.R0,
                ),
            ]
        else:
            steps = [
                self._step(
                    0, "Read a file", "mock_read_file", {"path": "~/notes.md"}, RiskLevel.R0
                ),
            ]

        return ExecutionPlan(
            task_id=task_id,
            summary=f"Plan for: {goal}",
            steps=steps,
        )

    @staticmethod
    def _step(
        index: int,
        title: str,
        tool: str,
        arguments: dict[str, object],
        risk: RiskLevel,
    ) -> PlanStep:
        return PlanStep(
            index=index,
            title=title,
            tool_name=tool,
            arguments=arguments,
            declared_risk=risk,
        )
