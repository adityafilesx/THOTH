"""Deterministic task state machine.

Every accepted transition emits an audit event BEFORE returning; rejected
transitions emit ``state.transition_rejected`` and leave state untouched.
Tool execution anywhere outside EXECUTING is impossible by construction —
the executor checks this machine, not the model's opinion.
"""

from collections.abc import Callable
from typing import Any

from thoth_daemon.schemas import TaskState

Emit = Callable[[str, dict[str, Any]], None]

TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.RECEIVED: frozenset({TaskState.UNDERSTANDING, TaskState.CANCELLED, TaskState.FAILED}),
    TaskState.UNDERSTANDING: frozenset({TaskState.PLANNING, TaskState.CANCELLED, TaskState.FAILED}),
    TaskState.PLANNING: frozenset({TaskState.RISK_REVIEW, TaskState.CANCELLED, TaskState.FAILED}),
    TaskState.RISK_REVIEW: frozenset(
        {
            TaskState.WAITING_FOR_APPROVAL,
            TaskState.EXECUTING,
            TaskState.CANCELLED,
            TaskState.FAILED,
        }
    ),
    TaskState.WAITING_FOR_APPROVAL: frozenset(
        {TaskState.EXECUTING, TaskState.CANCELLED, TaskState.FAILED}
    ),
    TaskState.EXECUTING: frozenset(
        {
            TaskState.VERIFYING,
            TaskState.RECOVERING,
            TaskState.WAITING_FOR_APPROVAL,  # a later plan step needs approval
            TaskState.CANCELLED,
            TaskState.FAILED,
        }
    ),
    TaskState.VERIFYING: frozenset(
        {
            TaskState.EXECUTING,  # advance to next step
            TaskState.COMPLETED,
            TaskState.RECOVERING,
            TaskState.CANCELLED,
            TaskState.FAILED,
        }
    ),
    TaskState.RECOVERING: frozenset({TaskState.EXECUTING, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


class InvalidTransitionError(Exception):
    def __init__(self, src: TaskState, dst: TaskState) -> None:
        super().__init__(f"invalid transition {src.value} -> {dst.value}")
        self.src = src
        self.dst = dst


class TaskStateMachine:
    def __init__(self, task_id: str, state: TaskState, emit: Emit) -> None:
        self._task_id = task_id
        self._state = state
        self._emit = emit

    @property
    def state(self) -> TaskState:
        return self._state

    def can_transition(self, dst: TaskState) -> bool:
        return dst in TRANSITIONS[self._state]

    def transition(self, dst: TaskState, reason: str) -> None:
        src = self._state
        if dst not in TRANSITIONS[src]:
            self._emit(
                "state.transition_rejected",
                {"from": src.value, "to": dst.value, "reason": reason},
            )
            raise InvalidTransitionError(src, dst)
        self._state = dst
        self._emit(
            "state.transition",
            {"from": src.value, "to": dst.value, "reason": reason},
        )
