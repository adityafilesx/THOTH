"""Skill engine (Phase 4 slice 5) — planning-only expansion of skill
templates into ExecutionPlans.

A skill is a declarative, parameterized plan template. ``expand`` binds
typed inputs into the template's steps and returns an ExecutionPlan that
enters the orchestrator exactly like any other plan (validation → policy
risk review → approvals → scoped execution → independent verification →
bounded recovery). The engine NEVER executes tools, and declared risks
are copied verbatim — effective risk is still max(tool default,
declared), so a skill can never lower a risk level or bypass approval.
"""

from __future__ import annotations

import re
from typing import Any

from thoth_daemon.schemas import (
    ExecutionPlan,
    PlanStep,
    RiskLevel,
    SkillDefinition,
    SkillStep,
    VerificationCheck,
    VerifierKind,
)
from thoth_daemon.storage.skills import SkillStore

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class SkillInputError(ValueError):
    """Missing, unknown, or extra skill input."""


class SkillEngine:
    def validate_inputs(self, skill: SkillDefinition, inputs: dict[str, str]) -> None:
        required = set(skill.inputs)
        provided = set(inputs)
        missing = required - provided
        extra = provided - required
        if missing:
            raise SkillInputError(f"missing inputs: {sorted(missing)}")
        if extra:
            raise SkillInputError(f"unexpected inputs: {sorted(extra)}")

    def expand(self, skill: SkillDefinition, inputs: dict[str, str], task_id: str) -> ExecutionPlan:
        self.validate_inputs(skill, inputs)

        def substitute(value: Any) -> Any:
            if isinstance(value, str):
                for match in _PLACEHOLDER.finditer(value):
                    if match.group(1) not in inputs:
                        raise SkillInputError(
                            f"unknown placeholder '{{{match.group(1)}}}' in skill '{skill.name}'"
                        )
                return _PLACEHOLDER.sub(lambda m: inputs[m.group(1)], value)
            if isinstance(value, dict):
                return {k: substitute(v) for k, v in value.items()}
            if isinstance(value, list):
                return [substitute(item) for item in value]
            return value

        steps = [
            PlanStep(
                index=i,
                title=substitute(step.title),
                tool_name=step.tool_name,
                arguments=substitute(step.arguments),
                declared_risk=step.declared_risk,  # verbatim; never lowered
                verification_checks=[
                    VerificationCheck.model_validate(substitute(c.model_dump()))
                    for c in step.verification_checks
                ],
            )
            for i, step in enumerate(skill.steps)
        ]
        return ExecutionPlan(task_id=task_id, summary=f"Skill: {skill.name}", steps=steps)


def _builtin_skills() -> list[SkillDefinition]:
    """The five built-in skills. Read-heavy by design; anything with side
    effects keeps its real risk level and flows through approvals."""
    return [
        SkillDefinition(
            name="continue-project",
            description="Re-orient inside a project: listing, git state, README.",
            inputs=["project_path"],
            workflow=[
                "List the project directory",
                "Show git status",
                "Read the README",
            ],
            steps=[
                SkillStep(
                    title="List {project_path}",
                    tool_name="fs_list_dir",
                    arguments={"path": "{project_path}"},
                    declared_risk=RiskLevel.R0,
                ),
                SkillStep(
                    title="Git status of {project_path}",
                    tool_name="git_status",
                    arguments={"cwd": "{project_path}"},
                    declared_risk=RiskLevel.R0,
                ),
                SkillStep(
                    title="Read the README",
                    tool_name="fs_read_file",
                    arguments={"path": "{project_path}/README.md"},
                    declared_risk=RiskLevel.R0,
                ),
            ],
        ),
        SkillDefinition(
            name="project-health-check",
            description="Inspect a repository's working-tree and recent history.",
            inputs=["project_path"],
            workflow=[
                "Show git status",
                "Show the five most recent commits",
                "List the project directory",
            ],
            steps=[
                SkillStep(
                    title="Git status of {project_path}",
                    tool_name="git_status",
                    arguments={"cwd": "{project_path}"},
                    declared_risk=RiskLevel.R0,
                ),
                SkillStep(
                    title="Recent commits",
                    tool_name="git_log",
                    arguments={"cwd": "{project_path}"},
                    declared_risk=RiskLevel.R0,
                ),
                SkillStep(
                    title="List {project_path}",
                    tool_name="fs_list_dir",
                    arguments={"path": "{project_path}"},
                    declared_risk=RiskLevel.R0,
                ),
            ],
        ),
        SkillDefinition(
            name="research-and-save",
            description="Read an approved web page and save its text locally.",
            inputs=["url", "dest_path"],
            workflow=[
                "Read the page text (approved domain only)",
                "Write it to the destination file",
                "Independently verify the file exists",
            ],
            steps=[
                SkillStep(
                    title="Read {url}",
                    tool_name="browser_read",
                    arguments={"url": "{url}"},
                    declared_risk=RiskLevel.R1,
                ),
                SkillStep(
                    title="Save research to {dest_path}",
                    tool_name="fs_write_file",
                    arguments={
                        "path": "{dest_path}",
                        "content": "Research notes from {url} (content captured separately)",
                    },
                    declared_risk=RiskLevel.R1,
                    verification_checks=[
                        VerificationCheck(
                            kind=VerifierKind.FILE_EXISTS, params={"path": "{dest_path}"}
                        )
                    ],
                ),
            ],
        ),
        SkillDefinition(
            name="prepare-git-commit",
            description="Stage work and show the diff — the human commits.",
            inputs=["repo_path"],
            workflow=[
                "Show git status",
                "Stage all changes",
                "Show the staged diff (no commit, no push)",
            ],
            steps=[
                SkillStep(
                    title="Git status of {repo_path}",
                    tool_name="git_status",
                    arguments={"cwd": "{repo_path}"},
                    declared_risk=RiskLevel.R0,
                ),
                SkillStep(
                    title="Stage changes",
                    tool_name="git_add",
                    arguments={"cwd": "{repo_path}", "paths": ["."]},
                    declared_risk=RiskLevel.R1,
                ),
                SkillStep(
                    title="Show staged diff",
                    tool_name="git_diff",
                    arguments={"cwd": "{repo_path}"},
                    declared_risk=RiskLevel.R0,
                ),
            ],
        ),
        SkillDefinition(
            name="organize-workspace",
            description="Report on a workspace's layout (read-only; no moves).",
            inputs=["workspace_path"],
            workflow=[
                "List the workspace",
                "Stat the workspace root",
            ],
            steps=[
                SkillStep(
                    title="List {workspace_path}",
                    tool_name="fs_list_dir",
                    arguments={"path": "{workspace_path}"},
                    declared_risk=RiskLevel.R0,
                ),
                SkillStep(
                    title="Stat {workspace_path}",
                    tool_name="fs_stat",
                    arguments={"path": "{workspace_path}"},
                    declared_risk=RiskLevel.R0,
                ),
            ],
        ),
    ]


async def seed_builtin_skills(store: SkillStore) -> list[SkillDefinition]:
    """Insert the built-in skills once; existing names are left untouched
    (idempotent). Returns only the newly created skills."""
    existing = {s.name for s in await store.list_skills()}
    created: list[SkillDefinition] = []
    for skill in _builtin_skills():
        if skill.name not in existing:
            await store.add_skill(skill)
            created.append(skill)
    return created
