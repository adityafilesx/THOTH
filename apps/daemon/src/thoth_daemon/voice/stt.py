"""Speech-to-text adapters (Phase 4 slice 6).

A transcript is USER-ADJACENT input: it may become a task GOAL through
the normal submit pipeline (source=voice) but it can NEVER approve an
action, expand permissions, or modify policy — the API layer only ever
turns it into a new task.

``FasterWhisperSTTAdapter`` is the real local-model implementation and is
**pending live verification** (requires the faster-whisper package, a
downloaded model, and microphone-captured audio). ``MockSTTAdapter`` is
the deterministic test double. Audio bytes are never logged.

Push-to-talk protocol (desktop side, future wiring): the desktop captures
audio client-side while the PTT key is held (MediaRecorder), then POSTs
the encoded bytes to /api/voice/transcribe (preview) or /api/voice/task
(transcribe + submit as a task). The daemon never touches the microphone.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    confidence: float
    duration_s: float
    language: str


class STTUnavailableError(Exception):
    """The STT backend is not installed/configured in this environment."""


class STTAdapter(Protocol):
    async def transcribe(self, audio_bytes: bytes, mime: str) -> Transcript: ...


class MockSTTAdapter:
    """MOCK — returns a primed transcript and records what it received."""

    def __init__(self, transcript: Transcript | None = None) -> None:
        self._transcript = transcript or Transcript(
            text="[mock transcription]", confidence=0.5, duration_s=0.0, language="en"
        )
        self.received: list[tuple[int, str]] = []  # (byte length, mime) — never the audio

    async def transcribe(self, audio_bytes: bytes, mime: str) -> Transcript:
        self.received.append((len(audio_bytes), mime))
        return self._transcript


class FasterWhisperSTTAdapter:
    """Local faster-whisper model. Pending live verification (needs the
    package, a model download, and real captured audio)."""

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size

    async def transcribe(self, audio_bytes: bytes, mime: str) -> Transcript:
        try:
            # Optional dependency; pending live verification.
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except ImportError as exc:
            raise STTUnavailableError(
                "faster-whisper is not installed; run `uv add faster-whisper` and "
                "download a model to enable local STT (pending live verification)"
            ) from exc

        def _run() -> Transcript:
            model = WhisperModel(self._model_size, device="auto")
            # Audio bytes go to a private temp file, removed immediately after.
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
                fh.write(audio_bytes)
                path = fh.name
            try:
                segments, info = model.transcribe(path)
                text = " ".join(segment.text.strip() for segment in segments).strip()
                return Transcript(
                    text=text,
                    confidence=float(getattr(info, "language_probability", 0.0)),
                    duration_s=float(getattr(info, "duration", 0.0)),
                    language=str(getattr(info, "language", "unknown")),
                )
            finally:
                os.unlink(path)

        return await asyncio.to_thread(_run)


def default_stt_adapter() -> STTAdapter:
    """Mock unless THOTH_STT=whisper — the live path is opt-in and pending
    live verification."""
    if os.environ.get("THOTH_STT") == "whisper":
        return FasterWhisperSTTAdapter()
    return MockSTTAdapter()
