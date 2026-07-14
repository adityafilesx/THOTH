"""Unified text command entry point with deterministic reflex dispatch."""

from typing import Any, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.api.operational import build_task_payload, refresh_dialogue
from thoth_daemon.core.command_dispatch import CommandDispatcher
from thoth_daemon.schemas import TaskSource

router = APIRouter()


class CommandBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    source: TaskSource = TaskSource.TEXT


def _dispatcher(request: Request) -> CommandDispatcher:
    return cast(CommandDispatcher, request.app.state.command_dispatcher)


def _serialize_control(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    return model_dump(mode="json") if callable(model_dump) else value


@router.post("/api/commands")
async def submit_command(body: CommandBody, request: Request) -> dict[str, Any]:
    result = await _dispatcher(request).dispatch(body.text, body.source)
    task_payload = None
    if result.task is not None:
        refresh_dialogue(request, result.task)
        task_payload = await build_task_payload(request, result.task)
    return {
        "route": result.intent.model_dump(mode="json"),
        "control": result.control,
        "control_result": _serialize_control(result.control_result),
        "response": result.response.model_dump(mode="json") if result.response else None,
        "task": task_payload,
    }
