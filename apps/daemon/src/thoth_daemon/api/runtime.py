from typing import Any, cast

from fastapi import APIRouter, Request

from thoth_daemon.core.local_runtime import LocalAIRuntimeManager

router = APIRouter()


@router.get("/api/runtime")
async def local_runtime_status(request: Request) -> dict[str, Any]:
    manager = cast(LocalAIRuntimeManager, request.app.state.local_runtime)
    return manager.snapshot().model_dump(mode="json")
