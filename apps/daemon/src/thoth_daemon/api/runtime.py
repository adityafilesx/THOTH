from typing import Any, cast

from fastapi import APIRouter, Request

from thoth_daemon.core.local_runtime import LocalAIRuntimeManager
from thoth_daemon.voice.metrics import VoiceLatencyMetrics

router = APIRouter()


@router.get("/api/runtime")
async def local_runtime_status(request: Request) -> dict[str, Any]:
    manager = cast(LocalAIRuntimeManager, request.app.state.local_runtime)
    metrics = cast(VoiceLatencyMetrics, request.app.state.voice_metrics)
    payload = manager.snapshot().model_dump(mode="json")
    payload["voice_latency"] = metrics.snapshot().model_dump(mode="json")
    return payload
