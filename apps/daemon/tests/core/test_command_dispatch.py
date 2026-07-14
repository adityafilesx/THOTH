from pathlib import Path
from typing import Any

from thoth_daemon.core.command_dispatch import CommandDispatcher
from thoth_daemon.core.intent_router import ReflexKind, RouteTier
from thoth_daemon.schemas import ExecutionPlan, Task, TaskSource, TaskState, WorkspaceProfile


class FakeOrchestrator:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, TaskSource]] = []
        self.plans: list[ExecutionPlan] = []
        self.tasks: list[Task] = []

    async def submit(self, goal: str, source: TaskSource = TaskSource.TEXT) -> Task:
        self.submitted.append((goal, source))
        task = Task(goal=goal, source=source, state=TaskState.COMPLETED)
        self.tasks.append(task)
        return task

    async def submit_plan(
        self,
        goal: str,
        plan: ExecutionPlan,
        source: TaskSource = TaskSource.TEXT,
    ) -> Task:
        self.plans.append(plan)
        task = Task(goal=goal, source=source, state=TaskState.COMPLETED, plan=plan)
        self.tasks.append(task)
        return task

    async def settle(self, task_id: str) -> Task:
        return next(task for task in self.tasks if task.id == task_id)

    def list_tasks(self) -> list[Task]:
        return list(self.tasks)


class FakeStop:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    async def stop(self, *, reason: str) -> dict[str, Any]:
        self.reasons.append(reason)
        return {"reason": reason}


class FakeSpeech:
    async def interrupt(self) -> bool:
        return True


class EmptySkills:
    async def list_skills(self) -> list[Any]:
        return []


def _dispatcher(tmp_path: Path) -> tuple[CommandDispatcher, FakeOrchestrator, FakeStop]:
    orchestrator = FakeOrchestrator()
    stop = FakeStop()
    workspace = WorkspaceProfile(name="THOTH", root_path=str(tmp_path), trusted=True)
    dispatcher = CommandDispatcher(
        orchestrator=orchestrator,
        stop=stop,
        speech=FakeSpeech(),
        skills=EmptySkills(),
        workspace=workspace,
        known_apps={"Finder", "TextEdit", "Visual Studio Code"},
    )
    return dispatcher, orchestrator, stop


async def test_typed_stop_never_reaches_the_planner(tmp_path: Path) -> None:
    dispatcher, orchestrator, stop = _dispatcher(tmp_path)

    result = await dispatcher.dispatch("thoth stop", TaskSource.TEXT)

    assert result.intent.tier is RouteTier.REFLEX
    assert result.intent.reflex_kind is ReflexKind.STOP
    assert result.control == "stopped"
    assert result.response is not None
    assert result.response.display.text == "Stopped. No external action was taken."
    assert stop.reasons == ["typed_command"]
    assert orchestrator.submitted == []
    assert orchestrator.plans == []


async def test_known_app_launch_uses_authoritative_plan_without_model(tmp_path: Path) -> None:
    dispatcher, orchestrator, _ = _dispatcher(tmp_path)

    result = await dispatcher.dispatch("open TextEdit", TaskSource.VOICE)

    assert result.task is not None
    assert result.intent.reflex_kind is ReflexKind.OPEN_APP
    assert orchestrator.submitted == []
    assert len(orchestrator.plans) == 1
    step = orchestrator.plans[0].steps[0]
    assert step.tool_name == "app_launch"
    assert step.arguments == {"app": "TextEdit"}


async def test_speech_interrupt_is_a_model_free_no_task_control(tmp_path: Path) -> None:
    dispatcher, orchestrator, _ = _dispatcher(tmp_path)

    result = await dispatcher.dispatch("stop speaking", TaskSource.VOICE)

    assert result.task is None
    assert result.control == "speech_interrupted"
    assert result.control_result is True
    assert result.response is not None
    assert result.response.display.text == "Speech stopped."
    assert orchestrator.submitted == []


async def test_novel_command_enters_planner_once(tmp_path: Path) -> None:
    dispatcher, orchestrator, _ = _dispatcher(tmp_path)

    result = await dispatcher.dispatch("inspect this project for problems", TaskSource.TEXT)

    assert result.intent.tier is RouteTier.PLANNER
    assert result.task is not None
    assert orchestrator.submitted == [("inspect this project for problems", TaskSource.TEXT)]
