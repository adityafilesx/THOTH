"""Read-only Phase 5.2/5.3 presentation and operational-context APIs."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.core.application_profiles import ApplicationProfileRegistry
from thoth_daemon.core.dialogue import (
    ApprovalFollowUpRejected,
    ArtifactReference,
    DialogueError,
    DialogueExpired,
    DialogueState,
    OperationalDialogueStore,
    constraints_from_text,
)
from thoth_daemon.core.foreground import ForegroundContext, ForegroundContextBroker
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.persona import (
    PersonaResponseComposer,
    ResponseFact,
    ResponseMode,
)
from thoth_daemon.core.persona_summary import PersonaSummaryComposer
from thoth_daemon.core.runtime_status import LocalRuntimeMonitor
from thoth_daemon.core.task_presentation import TaskPresentationComposer
from thoth_daemon.inference.base import InferenceProvider
from thoth_daemon.schemas import Task
from thoth_daemon.storage.permissions import PermissionStore

router = APIRouter()
_DIALOGUE_TTL = timedelta(minutes=5)


class PersonaComposeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact: ResponseFact
    mode: ResponseMode = ResponseMode.STANDARD
    use_local_summary: bool = False


class DialogueResolveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


def _orch(request: Request) -> Orchestrator:
    return cast(Orchestrator, request.app.state.orchestrator)


def _dialogue(request: Request) -> OperationalDialogueStore:
    return cast(OperationalDialogueStore, request.app.state.dialogue)


def _pending_for(request: Request, task_id: str) -> list[Any]:
    return [
        approval for approval in _orch(request).pending_approvals() if approval.task_id == task_id
    ]


def refresh_dialogue(request: Request, task: Task) -> DialogueState:
    """Refresh after a task-changing API operation; reads never extend TTL."""
    now = datetime.now(UTC)
    store = _dialogue(request)
    previous: DialogueState | None = None
    with contextlib.suppress(DialogueExpired):
        previous = store.get(task.id, now)

    artifacts = list(previous.referenced_artifacts if previous else ())
    verified_result_id = previous.previous_verified_result_id if previous else None
    if task.plan:
        for step in task.plan.steps:
            if step.verification_passed is True:
                verified_result_id = step.id
                path = None
                if step.tool_name == "fs_write_file":
                    path = step.arguments.get("path")
                elif step.tool_name == "browser_screenshot":
                    path = step.arguments.get("dest_path")
                if (
                    isinstance(path, str)
                    and Path(path).is_file()
                    and not any(artifact.artifact_id == step.id for artifact in artifacts)
                ):
                    artifacts.append(
                        ArtifactReference(
                            artifact_id=step.id,
                            task_id=task.id,
                            workspace_id=request.app.state.default_workspace.id,
                            path=path,
                            created_at=now,
                            authoritative=True,
                        )
                    )

    constraints = list(previous.constraints if previous else ())
    for constraint in constraints_from_text(task.goal):
        if constraint not in constraints:
            constraints.append(constraint)
    pending = _pending_for(request, task.id)
    state = DialogueState(
        active_task_id=task.id,
        workspace_id=request.app.state.default_workspace.id,
        referenced_artifacts=tuple(artifacts),
        previous_verified_result_id=verified_result_id,
        pending_question_id=None,
        pending_approval_id=pending[0].id if pending else None,
        constraints=tuple(constraints),
        expires_at=now + _DIALOGUE_TTL,
    )
    store.put(state)
    return state


async def build_task_payload(request: Request, task: Task) -> dict[str, Any]:
    now = datetime.now(UTC)
    monitor = cast(LocalRuntimeMonitor, request.app.state.runtime_monitor)
    runtime_status = await monitor.status()
    foreground: ForegroundContext | None = None
    try:
        broker = cast(ForegroundContextBroker, request.app.state.foreground)
        foreground = broker.capture(reason="task_response", task_id=task.id, now=now)
    except Exception:
        # A missing desktop session/AppKit yields no foreground evidence; it
        # never becomes a fabricated context or a task failure.
        foreground = None
    try:
        dialogue_expires = _dialogue(request).get(task.id, now).expires_at
    except DialogueExpired:
        dialogue_expires = None
    focus_result = request.app.state.focus_results.get(task.id)
    presentation = TaskPresentationComposer().compose(
        task,
        pending_approvals=_pending_for(request, task.id),
        runtime_status=runtime_status,
        foreground=foreground,
        focus_result=focus_result,
        dialogue_expires_at=dialogue_expires,
    )
    payload = task.model_dump(mode="json")
    payload["presentation"] = presentation.model_dump(mode="json")
    return payload


@router.get("/api/operational-status/{task_id}")
async def operational_status(task_id: str, request: Request) -> dict[str, Any]:
    task = _orch(request).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    payload = await build_task_payload(request, task)
    return cast(dict[str, Any], payload["presentation"])


@router.get("/api/foreground")
async def capture_foreground(
    request: Request,
    reason: str = Query(default="user_requested", min_length=1, max_length=80),
    task_id: str | None = None,
) -> dict[str, Any]:
    broker = cast(ForegroundContextBroker, request.app.state.foreground)
    try:
        context = broker.capture(reason=reason, task_id=task_id, now=datetime.now(UTC))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"foreground unavailable: {exc}") from exc
    return context.model_dump(mode="json")


@router.get("/api/application-profiles")
async def application_profiles(request: Request) -> list[dict[str, Any]]:
    profiles = cast(ApplicationProfileRegistry, request.app.state.application_profiles)
    return [profile.model_dump(mode="json") for profile in profiles.all()]


@router.get("/api/dialogue/{task_id}")
async def get_dialogue(task_id: str, request: Request) -> dict[str, Any]:
    try:
        state = _dialogue(request).get(task_id, datetime.now(UTC))
    except DialogueExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return state.model_dump(mode="json")


@router.post("/api/dialogue/{task_id}/resolve")
async def resolve_dialogue(
    task_id: str, body: DialogueResolveBody, request: Request
) -> dict[str, Any]:
    permissions = cast(PermissionStore, request.app.state.permissions)
    authorized = {workspace.id for workspace in await permissions.list_workspaces()}
    try:
        resolution = _dialogue(request).resolve_follow_up(
            task_id,
            body.text,
            datetime.now(UTC),
            authorized_workspace_ids=authorized,
        )
    except (DialogueError, ApprovalFollowUpRejected) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return resolution.model_dump(mode="json")


@router.post("/api/persona/compose")
async def compose_persona(body: PersonaComposeBody, request: Request) -> dict[str, Any]:
    if body.use_local_summary:
        provider = cast(InferenceProvider, request.app.state.inference_provider)
        response = await PersonaSummaryComposer().compose(body.fact, provider, body.mode)
    else:
        response = PersonaResponseComposer().compose(body.fact, body.mode)
    # This endpoint is a phrasing preview. Real task UI must use the
    # authoritative presentation derived from task state above.
    return {"authoritative": False, "response": response.model_dump(mode="json")}
