"""Short-lived operational dialogue state.

This is in-process context, not long-term memory. It resolves only recent,
authoritative objects already associated with the same task. It cannot approve
actions, expand workspace scope, lower risk, or execute tools.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DialogueConstraint(StrEnum):
    NO_PUSH = "no_push"


class DialogueIntent(StrEnum):
    OPEN_ARTIFACT = "open_artifact"
    RUN_TESTS = "run_tests"
    COMMIT_CHANGES = "commit_changes"
    ADD_CONSTRAINT = "add_constraint"
    USE_WORKSPACE = "use_workspace"
    RETRY_VERIFIED_RESULT = "retry_verified_result"
    STOP_FRONTEND = "stop_frontend"
    UNKNOWN = "unknown"


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    created_at: datetime
    authoritative: bool = False


class DialogueState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    active_task_id: str = Field(min_length=1)
    workspace_id: str | None = None
    referenced_artifacts: tuple[ArtifactReference, ...] = ()
    previous_verified_result_id: str | None = None
    pending_question_id: str | None = None
    pending_approval_id: str | None = None
    constraints: tuple[DialogueConstraint, ...] = ()
    expires_at: datetime

    @model_validator(mode="after")
    def _task_isolation(self) -> DialogueState:
        if any(a.task_id != self.active_task_id for a in self.referenced_artifacts):
            raise ValueError("artifact references must belong to the active task")
        if len(set(self.constraints)) != len(self.constraints):
            raise ValueError("dialogue constraints must be unique")
        return self


class DialogueResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: DialogueIntent
    active_task_id: str
    workspace_id: str | None = None
    artifact_id: str | None = None
    previous_verified_result_id: str | None = None
    constraints: tuple[DialogueConstraint, ...] = ()


class DialogueError(Exception):
    pass


class DialogueExpired(DialogueError):
    pass


class DialogueAmbiguous(DialogueError):
    pass


class DialogueScopeViolation(DialogueError):
    pass


class ApprovalFollowUpRejected(DialogueError):
    pass


_VAGUE_APPROVAL = re.compile(r"^(yes|approve( it)?|go ahead|do it)[.! ]*$", re.IGNORECASE)
_NO_PUSH = re.compile(r"\b(?:do not|don't|never)\s+push\b", re.IGNORECASE)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().replace("\u2019", "'"))


def constraints_from_text(text: str) -> tuple[DialogueConstraint, ...]:
    """Extract only deterministic, system-recognized hard constraints."""
    normalized = text.replace("\u2019", "'")
    return (DialogueConstraint.NO_PUSH,) if _NO_PUSH.search(normalized) else ()


def enforce_constraints(constraints: tuple[DialogueConstraint, ...], tool_name: str) -> None:
    if DialogueConstraint.NO_PUSH in constraints and tool_name in {
        "git_push",
        "mock_git_push",
    }:
        raise DialogueScopeViolation("no_push constraint forbids this tool")


class OperationalDialogueStore:
    """Process-local state. Constructing a new store represents a restart."""

    def __init__(self) -> None:
        self._states: dict[str, DialogueState] = {}

    def put(self, state: DialogueState) -> None:
        self._states[state.active_task_id] = state

    def get(self, task_id: str, now: datetime) -> DialogueState:
        state = self._states.get(task_id)
        if state is None:
            raise DialogueExpired("no active dialogue state for this task")
        if state.expires_at <= now:
            self._states.pop(task_id, None)
            raise DialogueExpired("dialogue state expired")
        return state

    def select_workspace(
        self,
        task_id: str,
        requested_workspace_id: str,
        authorized_workspace_ids: set[str],
        now: datetime,
    ) -> DialogueState:
        state = self.get(task_id, now)
        if requested_workspace_id not in authorized_workspace_ids:
            raise DialogueScopeViolation("dialogue cannot select an unapproved workspace")
        updated = state.model_copy(update={"workspace_id": requested_workspace_id})
        self.put(updated)
        return updated

    def enforce_tool_constraints(self, task_id: str, tool_name: str, now: datetime) -> None:
        state = self.get(task_id, now)
        enforce_constraints(state.constraints, tool_name)

    def resolve_follow_up(
        self,
        task_id: str,
        text: str,
        now: datetime,
        *,
        authorized_workspace_ids: set[str] | None = None,
    ) -> DialogueResolution:
        state = self.get(task_id, now)
        normalized = _normalize(text)

        if state.pending_approval_id and _VAGUE_APPROVAL.fullmatch(normalized):
            raise ApprovalFollowUpRejected(
                "dialogue cannot approve; use the invocation-bound approval endpoint"
            )

        if normalized in {"open it", "open it."}:
            return self._resolve_artifact(state, now)

        if normalized in {"don't push", "don't push."}:
            constraints = tuple(dict.fromkeys((*state.constraints, DialogueConstraint.NO_PUSH)))
            updated = state.model_copy(update={"constraints": constraints})
            self.put(updated)
            return self._resolution(updated, DialogueIntent.ADD_CONSTRAINT)

        if normalized in {"use the other workspace", "use the other workspace."}:
            if authorized_workspace_ids is None:
                raise DialogueScopeViolation("authorized workspace set is required")
            choices = set(authorized_workspace_ids)
            if state.workspace_id is not None:
                choices.discard(state.workspace_id)
            if len(choices) != 1:
                raise DialogueAmbiguous("the other workspace is ambiguous")
            updated = self.select_workspace(task_id, choices.pop(), authorized_workspace_ids, now)
            return self._resolution(updated, DialogueIntent.USE_WORKSPACE)

        if normalized in {"run the tests", "run the tests."}:
            return self._resolution(state, DialogueIntent.RUN_TESTS)
        if normalized in {"commit those changes", "commit those changes."}:
            return self._resolution(state, DialogueIntent.COMMIT_CHANGES)
        if normalized in {"try again", "try again."}:
            if not state.previous_verified_result_id:
                raise DialogueExpired("no recent verified result to retry")
            return self._resolution(state, DialogueIntent.RETRY_VERIFIED_RESULT)
        if normalized in {"stop the frontend", "stop the frontend."}:
            return self._resolution(state, DialogueIntent.STOP_FRONTEND)
        return self._resolution(state, DialogueIntent.UNKNOWN)

    def _resolve_artifact(self, state: DialogueState, now: datetime) -> DialogueResolution:
        candidates = [
            artifact
            for artifact in state.referenced_artifacts
            if artifact.authoritative
            and artifact.created_at <= now
            and artifact.task_id == state.active_task_id
            and Path(artifact.path).is_file()
        ]
        if not candidates:
            raise DialogueExpired("no authoritative recent artifact")
        if len(candidates) > 1:
            raise DialogueAmbiguous("multiple recent artifacts match 'it'")
        return DialogueResolution(
            intent=DialogueIntent.OPEN_ARTIFACT,
            active_task_id=state.active_task_id,
            workspace_id=state.workspace_id,
            artifact_id=candidates[0].artifact_id,
            previous_verified_result_id=state.previous_verified_result_id,
            constraints=state.constraints,
        )

    @staticmethod
    def _resolution(state: DialogueState, intent: DialogueIntent) -> DialogueResolution:
        return DialogueResolution(
            intent=intent,
            active_task_id=state.active_task_id,
            workspace_id=state.workspace_id,
            previous_verified_result_id=state.previous_verified_result_id,
            constraints=state.constraints,
        )
