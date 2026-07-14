"""Voice endpoints (Phase 4 slice 6).

- POST /api/voice/transcribe  — raw audio bytes -> Transcript (preview).
- POST /api/voice/task        — transcribe, then submit the text as a NEW
  task through the normal pipeline (source=voice). A transcript is never
  an approval: it cannot touch the ApprovalEngine, expand scope, or
  modify policy — it only ever becomes a task goal.
- POST /api/voice/say         — speak a status line (interruptible).
- POST /api/voice/interrupt   — stop the current utterance.

Audio bytes are never logged or retained. whisper.cpp is the local default;
missing runtime/model state returns 503 and never falls back to cloud speech.
"""

import logging
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.api.operational import build_task_payload, refresh_dialogue
from thoth_daemon.core.local_runtime import RuntimeUnavailable
from thoth_daemon.core.orchestrator import Orchestrator
from thoth_daemon.core.persona import (
    PersonaResponseComposer,
    ResponseFact,
    ResponseIntent,
    SpokenResponse,
)
from thoth_daemon.schemas import TaskSource
from thoth_daemon.voice.contracts import AudioCaptureMode
from thoth_daemon.voice.service import VoiceCommandService, VoiceSessionRegistry
from thoth_daemon.voice.session import TranscriptCorrectionExpired
from thoth_daemon.voice.stop import GlobalStopAuthority
from thoth_daemon.voice.stt import STTAdapter, STTUnavailableError
from thoth_daemon.voice.tts import SpeechSynthesisService

router = APIRouter()
logger = logging.getLogger(__name__)


class SayBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class StartSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AudioCaptureMode = AudioCaptureMode.HOLD


class EditTranscriptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class StopBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal["global_button", "escape", "menu_bar"]


def _stt(request: Request) -> STTAdapter:
    return cast(STTAdapter, request.app.state.stt)


def _tts(request: Request) -> SpeechSynthesisService:
    return cast(SpeechSynthesisService, request.app.state.speech_synthesis)


def _sessions(request: Request) -> VoiceSessionRegistry:
    return cast(VoiceSessionRegistry, request.app.state.voice_sessions)


def _commands(request: Request) -> VoiceCommandService:
    return cast(VoiceCommandService, request.app.state.voice_commands)


def _stop(request: Request) -> GlobalStopAuthority:
    return cast(GlobalStopAuthority, request.app.state.global_stop)


def _voice_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (STTUnavailableError, RuntimeUnavailable)):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, (RuntimeError, TranscriptCorrectionExpired)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


async def _transcribe(request: Request) -> Any:
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=422, detail="empty audio body")
    mime = request.headers.get("content-type", "application/octet-stream")
    try:
        return await _stt(request).transcribe(audio, mime)
    except STTUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _speak_safely(request: Request, response: SpokenResponse) -> None:
    """Keep optional local playback outside task truth and execution state."""
    try:
        await _tts(request).speak(response)
    except Exception:
        # A missing or failed local voice must not rewrite an authoritative
        # task result. Runtime health remains available through /api/runtime.
        logger.warning("voice_response_playback_failed", exc_info=True)


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
    refresh_dialogue(request, settled)
    payload = await build_task_payload(request, settled)
    spoken = SpokenResponse.model_validate(payload["presentation"]["response"]["spoken"])
    await _speak_safely(request, spoken)
    return payload


@router.post("/api/voice/say")
async def say(body: SayBody, request: Request) -> dict[str, Any]:
    handle = await _tts(request).speak(SpokenResponse(text=body.text))
    return {"speaking": handle is not None}


@router.post("/api/voice/interrupt")
async def interrupt(request: Request) -> dict[str, Any]:
    return {"interrupted": await _tts(request).interrupt()}


@router.post("/api/voice/sessions", status_code=201)
async def start_voice_session(body: StartSessionBody, request: Request) -> dict[str, Any]:
    snapshot = await _commands(request).start(body.mode)
    return snapshot.model_dump(mode="json")


@router.get("/api/voice/sessions/{session_id}")
async def get_voice_session(session_id: str, request: Request) -> dict[str, Any]:
    try:
        snapshot = _sessions(request).snapshot(session_id)
    except Exception as exc:
        raise _voice_error(exc) from exc
    return snapshot.model_dump(mode="json")


@router.put("/api/voice/sessions/{session_id}/audio")
async def append_voice_audio(session_id: str, request: Request) -> dict[str, Any]:
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=422, detail="empty audio body")
    mime = request.headers.get("content-type", "application/octet-stream")
    try:
        snapshot = _sessions(request).append_audio(session_id, audio, mime)
    except Exception as exc:
        raise _voice_error(exc) from exc
    return snapshot.model_dump(mode="json")


@router.post("/api/voice/sessions/{session_id}/partial")
async def recognise_voice_partial(session_id: str, request: Request) -> dict[str, Any]:
    try:
        snapshot = await _sessions(request).recognise_partial(session_id)
    except Exception as exc:
        raise _voice_error(exc) from exc
    return snapshot.model_dump(mode="json")


@router.post("/api/voice/sessions/{session_id}/finalise")
async def finalise_voice_session(session_id: str, request: Request) -> dict[str, Any]:
    try:
        snapshot = await _sessions(request).finalise(session_id)
    except Exception as exc:
        raise _voice_error(exc) from exc
    return snapshot.model_dump(mode="json")


@router.patch("/api/voice/sessions/{session_id}/transcript")
async def edit_voice_transcript(
    session_id: str,
    body: EditTranscriptBody,
    request: Request,
) -> dict[str, Any]:
    try:
        snapshot = _sessions(request).edit(session_id, body.text)
    except Exception as exc:
        raise _voice_error(exc) from exc
    return snapshot.model_dump(mode="json")


@router.post("/api/voice/sessions/{session_id}/submit")
async def submit_voice_session(session_id: str, request: Request) -> dict[str, Any]:
    try:
        result = await _commands(request).submit(session_id)
    except Exception as exc:
        raise _voice_error(exc) from exc
    if result.stopped:
        response = PersonaResponseComposer().compose(
            ResponseFact(intent=ResponseIntent.INTERRUPTED)
        )
        await _speak_safely(request, response.spoken)
        return {
            "stopped": True,
            "task": None,
            "stop": result.stop.model_dump(mode="json") if result.stop else None,
        }
    if result.task is None:
        raise HTTPException(status_code=409, detail="voice submission produced no task")
    refresh_dialogue(request, result.task)
    payload = await build_task_payload(request, result.task)
    spoken = SpokenResponse.model_validate(payload["presentation"]["response"]["spoken"])
    await _speak_safely(request, spoken)
    return {"stopped": False, "task": payload, "stop": None}


@router.delete("/api/voice/sessions/{session_id}")
async def cancel_voice_session(session_id: str, request: Request) -> dict[str, Any]:
    try:
        snapshot = _sessions(request).cancel(session_id)
    except Exception as exc:
        raise _voice_error(exc) from exc
    return snapshot.model_dump(mode="json")


@router.post("/api/stop")
async def global_stop(body: StopBody, request: Request) -> dict[str, Any]:
    result = await _stop(request).stop(reason=body.reason)
    return result.model_dump(mode="json")
