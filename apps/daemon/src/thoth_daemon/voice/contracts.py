"""Strict local speech contracts.

Speech text is user-adjacent input. These models describe recognition and
playback state only; they confer no approval, scope, risk, or execution
authority.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _VoiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VoiceActivityState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    SPEAKING = "speaking"
    SILENCE = "silence"
    FINALISING = "finalising"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


class AudioCaptureMode(StrEnum):
    HOLD = "hold"
    TOGGLE = "toggle"


class TranscriptSegment(_VoiceModel):
    text: str = Field(max_length=8_192)
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    final: bool

    @model_validator(mode="after")
    def _ordered_timestamps(self) -> TranscriptSegment:
        if self.end_s < self.start_s:
            raise ValueError("segment end must not precede start")
        return self


class PartialTranscript(_VoiceModel):
    text: str = Field(max_length=32_768)
    stable_text: str = Field(max_length=32_768)
    sequence: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    language: str = Field(min_length=2, max_length=32)
    observed_at: datetime
    final: bool = False


class FinalTranscript(_VoiceModel):
    text: str = Field(max_length=32_768)
    confidence: float = Field(ge=0, le=1)
    language: str = Field(min_length=2, max_length=32)
    duration_s: float = Field(ge=0)
    segments: tuple[TranscriptSegment, ...] = Field(default=(), max_length=512)
    completed_at: datetime
    final: bool = True


class SpeechRecognitionResult(_VoiceModel):
    transcript: FinalTranscript
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=512)
    language: str = Field(min_length=2, max_length=32)
    audio_deleted: bool
    elapsed_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def _language_matches(self) -> SpeechRecognitionResult:
        if self.language != self.transcript.language:
            raise ValueError("result language must match final transcript language")
        return self


class SpeechRecognitionHealth(_VoiceModel):
    available: bool
    provider: str
    model: str
    loaded: bool
    detail: str


class VoiceSessionSnapshot(_VoiceModel):
    session_id: str = Field(min_length=1, max_length=128)
    mode: AudioCaptureMode
    activity: VoiceActivityState
    microphone_visible: bool
    local_processing: bool = True
    partial: PartialTranscript | None = None
    final: FinalTranscript | None = None
    editable_text: str | None = Field(default=None, max_length=32_768)
    correction_expires_at: datetime | None = None
    submitted: bool = False


class SpeechRecognitionProvider(Protocol):
    async def health(self) -> SpeechRecognitionHealth: ...

    async def transcribe(self, audio_bytes: bytes, mime: str) -> SpeechRecognitionResult: ...

    async def unload(self) -> None: ...
