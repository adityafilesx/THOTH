"""In-memory push-to-talk and transcript correction lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from omnimac_daemon.voice.contracts import (
    FinalTranscript,
    PartialTranscript,
    VoiceActivityState,
)

MAX_CAPTURE_BYTES = 50 * 1024 * 1024


class DuplicateTranscriptSubmission(RuntimeError):
    """A final transcript has already entered the task pipeline."""


class TranscriptCorrectionExpired(RuntimeError):
    """The short-lived transcript correction window has elapsed."""


def _now() -> datetime:
    return datetime.now(UTC)


class AudioCaptureSession:
    """Operation-local audio buffer with an explicit visible lifecycle.

    Audio exists only in this in-memory object and is zeroised when the session
    finalises or cancels. Transcript submission is single-use.
    """

    def __init__(
        self,
        *,
        session_id: str,
        correction_window: timedelta = timedelta(seconds=3),
        clock: Callable[[], datetime] = _now,
        max_audio_bytes: int = MAX_CAPTURE_BYTES,
    ) -> None:
        if not session_id:
            raise ValueError("session_id is required")
        if correction_window.total_seconds() <= 0:
            raise ValueError("correction_window must be positive")
        self.session_id = session_id
        self._clock = clock
        self._correction_window = correction_window
        self._max_audio_bytes = max_audio_bytes
        self._audio = bytearray()
        self._activity = VoiceActivityState.IDLE
        self._partials: list[PartialTranscript] = []
        self._final: FinalTranscript | None = None
        self._editable_text: str | None = None
        self._correction_expires_at: datetime | None = None
        self._submitted = False

    @property
    def activity(self) -> VoiceActivityState:
        return self._activity

    @property
    def audio_size(self) -> int:
        return len(self._audio)

    @property
    def partials(self) -> tuple[PartialTranscript, ...]:
        return tuple(self._partials)

    @property
    def editable_text(self) -> str | None:
        return self._editable_text

    @property
    def final(self) -> FinalTranscript | None:
        return self._final

    @property
    def submitted(self) -> bool:
        return self._submitted

    @property
    def correction_expires_at(self) -> datetime | None:
        return self._correction_expires_at

    def start(self) -> None:
        if self._activity is not VoiceActivityState.IDLE:
            raise RuntimeError("capture session already started")
        self._activity = VoiceActivityState.LISTENING

    def append_audio(self, chunk: bytes) -> None:
        if self._activity not in {
            VoiceActivityState.LISTENING,
            VoiceActivityState.SPEAKING,
            VoiceActivityState.SILENCE,
        }:
            raise RuntimeError("audio capture is not active")
        if len(self._audio) + len(chunk) > self._max_audio_bytes:
            self.cancel()
            raise ValueError("audio capture exceeds the bounded size limit")
        self._audio.extend(chunk)

    def audio_bytes(self) -> bytes:
        return bytes(self._audio)

    def set_activity(self, activity: VoiceActivityState) -> None:
        if self._activity in {VoiceActivityState.CANCELLED, VoiceActivityState.COMPLETE}:
            raise RuntimeError("capture session is terminal")
        if activity not in {
            VoiceActivityState.LISTENING,
            VoiceActivityState.SPEAKING,
            VoiceActivityState.SILENCE,
            VoiceActivityState.FINALISING,
            VoiceActivityState.FAILED,
        }:
            raise ValueError("invalid live voice activity transition")
        self._activity = activity

    def publish_partial(self, partial: PartialTranscript) -> None:
        if self._final is not None or self._activity in {
            VoiceActivityState.CANCELLED,
            VoiceActivityState.COMPLETE,
        }:
            raise RuntimeError("partial transcript arrived after finalisation")
        if self._partials and partial.sequence <= self._partials[-1].sequence:
            raise ValueError("partial transcript sequence must increase")
        self._partials.append(partial)

    def finalise(self, transcript: FinalTranscript) -> None:
        if self._activity is VoiceActivityState.CANCELLED:
            raise RuntimeError("cancelled capture session cannot be finalised")
        if self._final is not None:
            raise DuplicateTranscriptSubmission("final transcript already exists")
        if self._activity is VoiceActivityState.IDLE:
            raise RuntimeError("capture session was not started")
        self._final = transcript
        self._editable_text = transcript.text
        self._correction_expires_at = self._clock() + self._correction_window
        self._clear_audio()
        self._activity = VoiceActivityState.COMPLETE

    def edit(self, text: str) -> None:
        if self._final is None or self._correction_expires_at is None:
            raise RuntimeError("there is no final transcript to edit")
        if self._clock() > self._correction_expires_at:
            raise TranscriptCorrectionExpired("transcript correction window expired")
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("transcript cannot be empty")
        self._editable_text = cleaned

    def submit(self) -> str:
        if self._submitted:
            raise DuplicateTranscriptSubmission("transcript was already submitted")
        if self._final is None or self._editable_text is None:
            raise RuntimeError("there is no final transcript to submit")
        self._submitted = True
        return self._editable_text

    def cancel(self) -> None:
        self._clear_audio()
        self._activity = VoiceActivityState.CANCELLED

    def fail(self) -> None:
        self._clear_audio()
        self._activity = VoiceActivityState.FAILED

    def _clear_audio(self) -> None:
        for index in range(len(self._audio)):
            self._audio[index] = 0
        self._audio.clear()
