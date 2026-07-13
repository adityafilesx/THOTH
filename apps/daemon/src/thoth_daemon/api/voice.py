"""Voice endpoints (Phase 4 slice 6).

- POST /api/voice/transcribe  — raw audio bytes -> Transcript (preview).
- POST /api/voice/task        — transcribe, then submit the text as a NEW
  task through the normal pipeline (source=voice). A transcript is never
  an approval: it cannot touch the ApprovalEngine, expand scope, or
  modify policy — it only ever becomes a task goal.
- POST /api/voice/say         — speak a status line (interruptible).
- POST /api/voice/interrupt   — stop the current utterance.

Audio bytes are never logged or persisted. The real STT backend is
pending live verification (model + microphone); the daemon defaults to
the mock unless THOTH_STT=whisper.
"""

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.schemas import TaskSource
from thoth_daemon.voice.stt import STTAdapter, STTUnavailableError
from thoth_daemon.voice.tts import TTSSpeaker

router = APIRouter()


class SayBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


def _stt(request: Request) -> STTAdapter:
    return cast(STTAdapter, request.app.state.stt)


def _tts(request: Request) -> TTSSpeaker:
    return cast(TTSSpeaker, request.app.state.tts)


async def _transcribe(request: Request) -> Any:
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=422, detail="empty audio body")
    mime = request.headers.get("content-type", "application/octet-stream")
    try:
        return await _stt(request).transcribe(audio, mime)
    except STTUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/voice/transcribe")
async def transcribe(request: Request) -> dict[str, Any]:
    transcript = await _transcribe(request)
    return dict(transcript.model_dump(mode="json"))


@router.post("/api/voice/task")
async def voice_task(request: Request) -> dict[str, Any]:
    transcript = await _transcribe(request)
    orch = cast(Orchestrator, request.app.state.orchestrator)
    task = await orch.submit(transcript.text, TaskSource.VOICE)
    settled = await orch.settle(task.id)
    return settled.model_dump(mode="json")


@router.post("/api/voice/say")
async def say(body: SayBody, request: Request) -> dict[str, Any]:
    await _tts(request).speak(body.text)
    return {"speaking": True}


@router.post("/api/voice/interrupt")
async def interrupt(request: Request) -> dict[str, Any]:
    return {"interrupted": await _tts(request).interrupt()}
