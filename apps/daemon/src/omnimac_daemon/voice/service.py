"""Push-to-talk session registry and normal-pipeline voice submission."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from omnimac_daemon.core.command_dispatch import CommandDispatcher
from omnimac_daemon.core.local_runtime import LocalAIRuntimeManager, RuntimeComponent
from omnimac_daemon.core.persona import PersonaResponse
from omnimac_daemon.schemas import Task, TaskSource
from omnimac_daemon.voice.contracts import (
    AudioCaptureMode,
    PartialTranscript,
    SpeechRecognitionProvider,
    SpeechRecognitionResult,
    VoiceActivityState,
    VoiceSessionSnapshot,
)
from omnimac_daemon.voice.metrics import VoiceLatencyMetrics, VoiceLatencyStage
from omnimac_daemon.voice.session import AudioCaptureSession
from omnimac_daemon.voice.stop import GlobalStopResult


def _now() -> datetime:
    return datetime.now(UTC)


class _SpeechInterruptor(Protocol):
    async def interrupt(self) -> bool: ...


@dataclass
class _ManagedSession:
    capture: AudioCaptureSession
    mode: AudioCaptureMode
    last_activity: datetime
    mime: str = "application/octet-stream"


class VoiceSubmissionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stopped: bool
    task: Task | None = None
    stop: GlobalStopResult | None = None
    control: str | None = None
    response: PersonaResponse | None = None


class VoiceSessionRegistry:
    """Short-lived in-memory voice state with optional transcript retention."""

    def __init__(
        self,
        provider: SpeechRecognitionProvider,
        *,
        retain_transcripts: bool = False,
        correction_window: timedelta = timedelta(seconds=3),
        session_ttl: timedelta = timedelta(minutes=2),
        clock: Callable[[], datetime] = _now,
        runtime: LocalAIRuntimeManager | None = None,
        metrics: VoiceLatencyMetrics | None = None,
    ) -> None:
        if session_ttl.total_seconds() <= 0:
            raise ValueError("session_ttl must be positive")
        self._provider = provider
        self._retain_transcripts = retain_transcripts
        self._correction_window = correction_window
        self._session_ttl = session_ttl
        self._clock = clock
        self._runtime = runtime
        self._metrics = metrics
        self._sessions: dict[str, _ManagedSession] = {}

    def start(self, mode: AudioCaptureMode) -> VoiceSessionSnapshot:
        started = perf_counter()
        session_id = str(uuid.uuid4())
        capture = AudioCaptureSession(
            session_id=session_id,
            correction_window=self._correction_window,
            clock=self._clock,
        )
        capture.start()
        self._sessions[session_id] = _ManagedSession(
            capture=capture,
            mode=mode,
            last_activity=self._clock(),
        )
        snapshot = self.snapshot(session_id)
        if self._metrics is not None:
            self._metrics.record(
                VoiceLatencyStage.RECORDING_START,
                (perf_counter() - started) * 1_000,
            )
        return snapshot

    def append_audio(self, session_id: str, chunk: bytes, mime: str) -> VoiceSessionSnapshot:
        managed = self._get(session_id)
        managed.capture.append_audio(chunk)
        managed.mime = mime
        self._touch(managed)
        return self.snapshot(session_id)

    async def recognise_partial(self, session_id: str) -> VoiceSessionSnapshot:
        started = perf_counter()
        managed = self._get(session_id)
        first_partial = not managed.capture.partials
        audio = managed.capture.audio_bytes()
        if not audio:
            raise ValueError("voice session has no audio")
        result = await self._transcribe(audio, managed.mime)
        previous = managed.capture.partials[-1].text if managed.capture.partials else ""
        partial = PartialTranscript(
            text=result.transcript.text,
            stable_text=_stable_prefix(previous, result.transcript.text),
            sequence=len(managed.capture.partials) + 1,
            confidence=result.transcript.confidence,
            language=result.transcript.language,
            observed_at=self._clock(),
        )
        managed.capture.publish_partial(partial)
        self._touch(managed)
        if first_partial and self._metrics is not None:
            self._metrics.record(
                VoiceLatencyStage.FIRST_PARTIAL,
                (perf_counter() - started) * 1_000,
            )
        return self.snapshot(session_id)

    async def finalise(self, session_id: str) -> VoiceSessionSnapshot:
        started = perf_counter()
        managed = self._get(session_id)
        audio = managed.capture.audio_bytes()
        if not audio:
            raise ValueError("voice session has no audio")
        managed.capture.set_activity(VoiceActivityState.FINALISING)
        try:
            result = await self._transcribe(audio, managed.mime)
            managed.capture.finalise(result.transcript)
            self._touch(managed)
        except BaseException:
            managed.capture.fail()
            raise
        snapshot = self.snapshot(session_id)
        if self._metrics is not None:
            self._metrics.record(
                VoiceLatencyStage.FINALISATION,
                (perf_counter() - started) * 1_000,
            )
        return snapshot

    def edit(self, session_id: str, text: str) -> VoiceSessionSnapshot:
        managed = self._get(session_id)
        managed.capture.edit(text)
        self._touch(managed)
        return self.snapshot(session_id)

    def consume(self, session_id: str) -> str:
        managed = self._get(session_id)
        text = managed.capture.submit()
        self._touch(managed)
        return text

    def finish_submission(self, session_id: str) -> None:
        if not self._retain_transcripts:
            self._sessions.pop(session_id, None)

    def cancel(self, session_id: str) -> VoiceSessionSnapshot:
        managed = self._get(session_id)
        managed.capture.cancel()
        snapshot = self.snapshot(session_id)
        # Cancellation is an explicit discard operation. Transcript retention
        # applies only to successfully finalised submissions, never to an
        # abandoned capture.
        self._sessions.pop(session_id, None)
        return snapshot

    def cancel_all(self) -> int:
        count = 0
        terminal = {
            VoiceActivityState.COMPLETE,
            VoiceActivityState.CANCELLED,
            VoiceActivityState.FAILED,
        }
        discarded: list[str] = []
        for session_id, managed in self._sessions.items():
            if managed.capture.activity not in terminal:
                managed.capture.cancel()
                count += 1
                discarded.append(session_id)
            elif managed.capture.activity is not VoiceActivityState.COMPLETE:
                discarded.append(session_id)
        for session_id in discarded:
            self._sessions.pop(session_id, None)
        if not self._retain_transcripts:
            # Default privacy mode retains no terminal transcript state.
            self._sessions.clear()
        return count

    def purge_expired(self) -> int:
        """Zero and remove abandoned sessions after the bounded local TTL."""

        now = self._clock()
        expired: list[str] = []
        for session_id, managed in self._sessions.items():
            if now - managed.last_activity <= self._session_ttl:
                continue
            if self._retain_transcripts and managed.capture.submitted:
                continue
            if managed.capture.activity not in {
                VoiceActivityState.COMPLETE,
                VoiceActivityState.CANCELLED,
                VoiceActivityState.FAILED,
            }:
                managed.capture.cancel()
            expired.append(session_id)
        for session_id in expired:
            self._sessions.pop(session_id, None)
        return len(expired)

    def snapshot(self, session_id: str) -> VoiceSessionSnapshot:
        managed = self._get(session_id)
        capture = managed.capture
        microphone_visible = capture.activity in {
            VoiceActivityState.LISTENING,
            VoiceActivityState.SPEAKING,
            VoiceActivityState.SILENCE,
        }
        return VoiceSessionSnapshot(
            session_id=session_id,
            mode=managed.mode,
            activity=capture.activity,
            microphone_visible=microphone_visible,
            partial=capture.partials[-1] if capture.partials else None,
            final=capture.final,
            editable_text=capture.editable_text,
            correction_expires_at=capture.correction_expires_at,
            submitted=capture.submitted,
        )

    def _get(self, session_id: str) -> _ManagedSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"voice session {session_id!r} was not found") from exc

    def _touch(self, managed: _ManagedSession) -> None:
        managed.last_activity = self._clock()

    async def _transcribe(self, audio: bytes, mime: str) -> SpeechRecognitionResult:
        if self._runtime is None:
            return await self._provider.transcribe(audio, mime)
        async with self._runtime.use(RuntimeComponent.SPEECH_RECOGNITION):
            return await self._provider.transcribe(audio, mime)


class VoiceCommandService:
    """Barge-in and submit voice text through the existing orchestrator."""

    def __init__(
        self,
        *,
        sessions: VoiceSessionRegistry,
        dispatcher: CommandDispatcher,
        tts: _SpeechInterruptor,
    ) -> None:
        self._sessions = sessions
        self._dispatcher = dispatcher
        self._tts = tts

    async def start(self, mode: AudioCaptureMode) -> VoiceSessionSnapshot:
        # Push-to-talk is authoritative user presence. Interrupt local speech
        # before opening capture so OmniMac cannot transcribe its own TTS.
        await self._tts.interrupt()
        return self._sessions.start(mode)

    async def submit(self, session_id: str) -> VoiceSubmissionResult:
        text = self._sessions.consume(session_id)
        try:
            dispatched = await self._dispatcher.dispatch(text, TaskSource.VOICE)
        finally:
            # The transcript is single-use. Remove the in-memory session on
            # every dispatch outcome so an exception cannot retain it.
            self._sessions.finish_submission(session_id)
        if dispatched.control == "stopped":
            stop = dispatched.control_result if isinstance(dispatched.control_result, GlobalStopResult) else None
            return VoiceSubmissionResult(
                stopped=True,
                stop=stop,
                control=dispatched.control,
                response=dispatched.response,
            )
        return VoiceSubmissionResult(
            stopped=False,
            task=dispatched.task,
            control=dispatched.control,
            response=dispatched.response,
        )


def _stable_prefix(previous: str, current: str) -> str:
    previous_words = previous.split()
    current_words = current.split()
    matching: list[str] = []
    for old, new in zip(previous_words, current_words, strict=False):
        if old != new:
            break
        matching.append(new)
    return " ".join(matching)
