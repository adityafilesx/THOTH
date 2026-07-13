from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.schemas import TaskSource

router = APIRouter()


class CreateTaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    source: TaskSource = TaskSource.TEXT


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    modified_arguments: dict[str, Any] | None = None


def _orch(request: Request) -> Orchestrator:
    return cast(Orchestrator, request.app.state.orchestrator)


@router.post("/api/tasks")
async def create_task(body: CreateTaskBody, request: Request) -> dict[str, Any]:
    task = await _orch(request).submit(body.goal, body.source)
    settled = await _orch(request).settle(task.id)
    return settled.model_dump(mode="json")


@router.get("/api/tasks")
async def list_tasks(request: Request) -> list[dict[str, Any]]:
    return [t.model_dump(mode="json") for t in _orch(request).list_tasks()]


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: str, request: Request) -> dict[str, Any]:
    task = _orch(request).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.model_dump(mode="json")


@router.get("/api/tasks/{task_id}/audit")
async def task_audit(task_id: str, request: Request) -> list[dict[str, Any]]:
    events = await _orch(request).task_audit(task_id)
    return [e.model_dump(mode="json") for e in events]


@router.get("/api/tasks/{task_id}/audit/verify")
async def verify_task_audit(task_id: str, request: Request) -> dict[str, Any]:
    """Recompute the task's tamper-evident hash chain and return the
    verification manifest (slice 9)."""
    audit = cast(AuditStore, request.app.state.audit)
    manifest = await audit.verify_chain(task_id)
    return manifest.model_dump(mode="json")


@router.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
    try:
        task = await _orch(request).cancel(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc
    return task.model_dump(mode="json")


@router.get("/api/approvals/pending")
async def pending_approvals(request: Request) -> list[dict[str, Any]]:
    return [a.model_dump(mode="json") for a in _orch(request).pending_approvals()]


@router.post("/api/approvals/{request_id}/decision")
async def decide_approval(request_id: str, body: DecisionBody, request: Request) -> dict[str, Any]:
    try:
        task = await _orch(request).decide_approval(
            request_id, body.approved, body.modified_arguments
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return task.model_dump(mode="json")
