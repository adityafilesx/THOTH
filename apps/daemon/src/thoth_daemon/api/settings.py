from typing import Any, cast

from fastapi import APIRouter, Request

import thoth_daemon
from thoth_daemon.config import Settings
from thoth_daemon.core.local_runtime import LocalAIRuntimeManager

router = APIRouter()


@router.get("/api/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    cfg = cast(Settings, request.app.state.settings)
    runtime = cast(LocalAIRuntimeManager, request.app.state.local_runtime)
    return {
        "version": thoth_daemon.__version__,
        "planner": cfg.planner,
        "approval_ttl_seconds": cfg.approval_ttl_seconds,
        "max_retries_per_step": cfg.max_retries_per_step,
        "max_retries_per_task": cfg.max_retries_per_task,
        "trusted_workspaces": cfg.trusted_workspaces,
        "inference_provider": cfg.inference_provider,
        "inference_model": cfg.inference_model,
        "network_isolation": cfg.network_isolation,
        "local_runtime": runtime.snapshot().model_dump(mode="json"),
    }
