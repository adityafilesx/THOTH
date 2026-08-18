"""Authoritative deterministic command dispatch shared by interaction surfaces.

The dispatcher classifies text before planning. Reflexes are converted into
trusted plans or control operations here; they never depend on model output.
All effectful plans still enter the normal orchestrator state machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from omnimac_daemon.core.intent_router import (
    IntentRouter,
    ReflexKind,
    RoutedIntent,
    RouteTier,
    build_skill_aliases,
)
from omnimac_daemon.core.persona import (
    PersonaResponse,
    PersonaResponseComposer,
    ResponseFact,
    ResponseIntent,
)
from omnimac_daemon.core.skill_engine import SkillEngine
from omnimac_daemon.schemas import (
    ExecutionPlan,
    PlanStep,
    RiskLevel,
    SkillDefinition,
    Task,
    TaskSource,
    WorkspaceProfile,
)


class _Orchestrator(Protocol):
    async def submit(self, goal: str, source: TaskSource = TaskSource.TEXT) -> Task: ...

    async def submit_plan(
        self,
        goal: str,
        plan: ExecutionPlan,
        source: TaskSource = TaskSource.TEXT,
    ) -> Task: ...

    async def settle(self, task_id: str) -> Task: ...

    def list_tasks(self) -> list[Task]: ...


class _StopAuthority(Protocol):
    async def stop(self, *, reason: str) -> Any: ...


class _SpeechInterruptor(Protocol):
    async def interrupt(self) -> bool: ...


class _SkillStore(Protocol):
    async def list_skills(self) -> list[SkillDefinition]: ...


@dataclass(frozen=True)
class CommandDispatchResult:
    intent: RoutedIntent
    task: Task | None = None
    control: str | None = None
    control_result: Any = None
    response: PersonaResponse | None = None


class CommandDispatcher:
    def __init__(
        self,
        *,
        orchestrator: _Orchestrator,
        stop: _StopAuthority,
        speech: _SpeechInterruptor,
        skills: _SkillStore,
        workspace: WorkspaceProfile,
        known_apps: set[str],
    ) -> None:
        self._orchestrator = orchestrator
        self._stop = stop
        self._speech = speech
        self._skills = skills
        self._workspace = workspace
        self._known_apps = known_apps

    async def dispatch(self, text: str, source: TaskSource) -> CommandDispatchResult:
        skills = await self._skills.list_skills()
        names = {skill.name for skill in skills if skill.enabled}
        router = IntentRouter(
            known_apps=self._known_apps,
            known_skills=names,
            known_workspaces={self._workspace.name, "OmniMac"},
            skill_aliases=build_skill_aliases(names),
        )
        intent = router.route(text)

        if intent.tier is RouteTier.CLARIFY:
            return CommandDispatchResult(
                intent=intent,
                control="clarification_required",
                response=PersonaResponseComposer().compose(
                    ResponseFact(
                        intent=ResponseIntent.NEEDS_CLARIFICATION,
                        clarification_question=(intent.clarification or "I need more specific authoritative context."),
                    )
                ),
            )

        if intent.tier is RouteTier.PLANNER:
            task = await self._orchestrator.submit(text.strip(), source)
            settled = await self._orchestrator.settle(task.id)
            return CommandDispatchResult(intent=intent, task=settled)

        kind = intent.reflex_kind
        if kind in {ReflexKind.STOP, ReflexKind.CANCEL}:
            reason = "voice_phrase" if source is TaskSource.VOICE else "typed_command"
            stopped = await self._stop.stop(reason=reason)
            response = PersonaResponseComposer().compose(ResponseFact(intent=ResponseIntent.INTERRUPTED))
            return CommandDispatchResult(
                intent=intent,
                control="stopped",
                control_result=stopped,
                response=response,
            )

        if kind in {ReflexKind.MUTE, ReflexKind.INTERRUPT}:
            interrupted = await self._speech.interrupt()
            return CommandDispatchResult(
                intent=intent,
                control="speech_interrupted",
                control_result=interrupted,
                response=PersonaResponseComposer().compose(
                    ResponseFact(
                        intent=ResponseIntent.ACKNOWLEDGEMENT,
                        summary="Speech stopped.",
                    )
                ),
            )

        if kind is ReflexKind.STATUS:
            tasks = self._orchestrator.list_tasks()
            latest_task = tasks[-1] if tasks else None
            return CommandDispatchResult(
                intent=intent,
                task=latest_task,
                control="status",
                response=(
                    None
                    if latest_task is not None
                    else PersonaResponseComposer().compose(
                        ResponseFact(
                            intent=ResponseIntent.ACKNOWLEDGEMENT,
                            summary="No task is running.",
                        )
                    )
                ),
            )

        if kind in {ReflexKind.DAEMON_STATUS, ReflexKind.START_BACKEND}:
            already_running = kind is ReflexKind.START_BACKEND
            return CommandDispatchResult(
                intent=intent,
                control="backend_already_running" if already_running else "daemon_running",
                response=PersonaResponseComposer().compose(
                    ResponseFact(
                        intent=ResponseIntent.ACKNOWLEDGEMENT,
                        summary=("The daemon is already running." if already_running else "The daemon is running."),
                    )
                ),
            )

        if kind is ReflexKind.OPEN_URL and intent.target:
            plan = ExecutionPlan(
                task_id="pending",
                summary=f"Open {intent.target}",
                steps=[
                    PlanStep(
                        index=0,
                        title=f"Open {intent.target}",
                        tool_name="sys_open_url",
                        arguments={"url": intent.target},
                        declared_risk=RiskLevel.R1,
                    )
                ],
            )
            task = await self._orchestrator.submit_plan(text.strip(), plan, source)
            settled = await self._orchestrator.settle(task.id)
            return CommandDispatchResult(intent=intent, task=settled)

        if kind in {ReflexKind.OPEN_APP, ReflexKind.FOCUS_APP} and intent.target:
            tool_name = "app_launch" if kind is ReflexKind.OPEN_APP else "app_focus"
            verb = "Open" if kind is ReflexKind.OPEN_APP else "Focus"
            plan = ExecutionPlan(
                task_id="pending",
                summary=f"{verb} {intent.target}",
                steps=[
                    PlanStep(
                        index=0,
                        title=f"{verb} {intent.target}",
                        tool_name=tool_name,
                        arguments={"app": intent.target},
                        declared_risk=RiskLevel.R1,
                    )
                ],
            )
            task = await self._orchestrator.submit_plan(text.strip(), plan, source)
            settled = await self._orchestrator.settle(task.id)
            return CommandDispatchResult(intent=intent, task=settled)

        if kind in {ReflexKind.RUN_SKILL, ReflexKind.CONTINUE_WORKSPACE}:
            skill_name = intent.target if kind is ReflexKind.RUN_SKILL else "continue-project"
            skill = next(
                (candidate for candidate in skills if candidate.enabled and candidate.name == skill_name),
                None,
            )
            if skill is not None:
                inputs = self._default_skill_inputs(skill)
                if inputs is not None:
                    plan = SkillEngine().expand(skill, inputs, task_id="pending")
                    task = await self._orchestrator.submit_plan(text.strip(), plan, source)
                    return CommandDispatchResult(
                        intent=intent,
                        task=await self._orchestrator.settle(task.id),
                    )

        # A recognized reflex with unavailable authoritative context must not
        # be reinterpreted by a model. Return a clarification control result.
        return CommandDispatchResult(
            intent=intent,
            control="clarification_required",
            response=PersonaResponseComposer().compose(
                ResponseFact(
                    intent=ResponseIntent.NEEDS_CLARIFICATION,
                    clarification_question=(intent.clarification or "I need more specific authoritative context."),
                )
            ),
        )

    def _default_skill_inputs(self, skill: SkillDefinition) -> dict[str, str] | None:
        if not skill.inputs:
            return {}
        if len(skill.inputs) == 1 and skill.inputs[0] in {"project_path", "repo_path", "workspace_path"} and self._workspace.trusted:
            return {skill.inputs[0]: self._workspace.root_path}
        return None
