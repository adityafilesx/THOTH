import pytest

from thoth_daemon.core.state_machine import (
    TRANSITIONS,
    InvalidTransitionError,
    TaskStateMachine,
)
from thoth_daemon.schemas import TERMINAL_STATES, TaskState

ALL_STATES = list(TaskState)

ALLOWED_PAIRS = [(src, dst) for src, dsts in TRANSITIONS.items() for dst in dsts]
INVALID_PAIRS = [
    (src, dst)
    for src in ALL_STATES
    for dst in ALL_STATES
    if dst not in TRANSITIONS[src]
]


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def __call__(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, payload))


@pytest.mark.parametrize(("src", "dst"), ALLOWED_PAIRS)
def test_every_allowed_transition(src: TaskState, dst: TaskState) -> None:
    recorder = Recorder()
    machine = TaskStateMachine(task_id="t1", state=src, emit=recorder)
    machine.transition(dst, reason="test")
    assert machine.state is dst
    assert recorder.events[-1][0] == "state.transition"
    assert recorder.events[-1][1]["from"] == src.value
    assert recorder.events[-1][1]["to"] == dst.value


@pytest.mark.parametrize(("src", "dst"), INVALID_PAIRS)
def test_every_invalid_transition_rejected(src: TaskState, dst: TaskState) -> None:
    recorder = Recorder()
    machine = TaskStateMachine(task_id="t1", state=src, emit=recorder)
    with pytest.raises(InvalidTransitionError):
        machine.transition(dst, reason="test")
    assert machine.state is src, "state must not change on a rejected transition"
    assert recorder.events[-1][0] == "state.transition_rejected"


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES, key=lambda s: s.value))
def test_terminal_states_are_frozen(terminal: TaskState) -> None:
    machine = TaskStateMachine(task_id="t1", state=terminal, emit=Recorder())
    for dst in ALL_STATES:
        with pytest.raises(InvalidTransitionError):
            machine.transition(dst, reason="test")


@pytest.mark.parametrize(
    "src", [s for s in ALL_STATES if s not in TERMINAL_STATES]
)
def test_cancellation_reachable_from_every_non_terminal_state(src: TaskState) -> None:
    machine = TaskStateMachine(task_id="t1", state=src, emit=Recorder())
    machine.transition(TaskState.CANCELLED, reason="user pressed stop")
    assert machine.state is TaskState.CANCELLED


def test_self_transition_is_invalid() -> None:
    machine = TaskStateMachine(task_id="t1", state=TaskState.EXECUTING, emit=Recorder())
    with pytest.raises(InvalidTransitionError):
        machine.transition(TaskState.EXECUTING, reason="noop")


def test_full_happy_path_emits_ordered_audit_trail() -> None:
    recorder = Recorder()
    machine = TaskStateMachine(task_id="t1", state=TaskState.RECEIVED, emit=recorder)
    path = [
        TaskState.UNDERSTANDING,
        TaskState.PLANNING,
        TaskState.RISK_REVIEW,
        TaskState.WAITING_FOR_APPROVAL,
        TaskState.EXECUTING,
        TaskState.VERIFYING,
        TaskState.COMPLETED,
    ]
    for state in path:
        machine.transition(state, reason="advance")
    assert [e[1]["to"] for e in recorder.events] == [s.value for s in path]
    assert all(e[0] == "state.transition" for e in recorder.events)
