"""Speech-to-text adapters (Phase 4 slice 6).

A transcript is USER-ADJACENT input: it may become a task GOAL through
the normal submit pipeline (source=voice) but it can NEVER approve an
action, expand permissions, or modify policy — the API layer only ever
turns it into a new task.

``WhisperCppSpeechRecognitionProvider`` is the primary local provider.
``FasterWhisperSTTAdapter`` remains a legacy optional adapter and
``MockSTTAdapter`` is an explicit deterministic test double. Audio bytes are
never logged.

Push-to-talk protocol (desktop side, future wiring): the desktop captures
audio client-side while the PTT key is held (MediaRecorder), then POSTs
the encoded bytes to /api/voice/transcribe (preview) or /api/voice/task
(transcribe + submit as a task). The daemon never touches the microphone.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import tempfile
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from thoth_daemon.voice.contracts import (
    FinalTranscript,
    SpeechRecognitionHealth,
    SpeechRecognitionProvider,
    SpeechRecognitionResult,
    TranscriptSegment,
)


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    confidence: float
    duration_s: float
    language: str


class STTUnavailableError(Exception):
    """The STT backend is not installed/configured in this environment."""


class SpeechRecognitionUnavailable(STTUnavailableError):
    """The configured local speech provider cannot run on this host."""


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


class MockSpeechRecognitionProvider:
    """MOCK provider for hermetic session and API tests."""

    def __init__(self, transcript: FinalTranscript) -> None:
        self._transcript = transcript
        self.received: list[tuple[int, str]] = []
        self.loaded = False

    async def health(self) -> SpeechRecognitionHealth:
        return SpeechRecognitionHealth(
            available=True,
            provider="mock",
            model="mock-local-speech",
            loaded=self.loaded,
            detail="deterministic mock speech provider",
        )

    async def transcribe(self, audio_bytes: bytes, mime: str) -> SpeechRecognitionResult:
        self.received.append((len(audio_bytes), mime))
        self.loaded = True
        return SpeechRecognitionResult(
            transcript=self._transcript,
            provider="mock",
            model="mock-local-speech",
            language=self._transcript.language,
            audio_deleted=True,
            elapsed_ms=0,
        )

    async def unload(self) -> None:
        self.loaded = False


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


WhisperRunner = Callable[[list[str], Path], Awaitable[tuple[int, str, str]]]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _run_whisper(argv: list[str], audio_path: Path) -> tuple[int, str, str]:
    del audio_path
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return (
        int(process.returncode or 0),
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


class WhisperCppSpeechRecognitionProvider:
    """Fully local whisper.cpp command provider.

    The command is argv-only and the operation-local audio file is mode 0600
    and deleted in a ``finally`` block, including cancellation and crashes.
    Model installation is explicit; absence is a typed degraded state and
    never triggers a cloud fallback.
    """

    def __init__(
        self,
        *,
        executable: Path = Path("/opt/homebrew/bin/whisper-cli"),
        model_path: Path = Path("data/models/whisper/ggml-base.en.bin"),
        language: str = "en",
        expected_executable_sha256: str | None = None,
        expected_model_sha256: str | None = None,
        runner: WhisperRunner = _run_whisper,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._executable = executable
        self._model_path = model_path
        self._language = language
        self._expected_executable_sha256 = expected_executable_sha256
        self._expected_model_sha256 = expected_model_sha256
        self._runner = runner
        self._clock = clock
        self._loaded = False

    @property
    def integrity_pinned(self) -> bool:
        return bool(self._expected_executable_sha256 and self._expected_model_sha256)

    async def health(self) -> SpeechRecognitionHealth:
        if not self._executable.is_file() or not os.access(self._executable, os.X_OK):
            return SpeechRecognitionHealth(
                available=False,
                provider="whisper.cpp",
                model=str(self._model_path),
                loaded=False,
                detail="whisper.cpp executable is unavailable",
            )
        if not self._model_path.is_file():
            return SpeechRecognitionHealth(
                available=False,
                provider="whisper.cpp",
                model=str(self._model_path),
                loaded=False,
                detail="local Whisper model is unavailable",
            )
        if self._expected_executable_sha256:
            executable_hash = await asyncio.to_thread(_sha256_file, self._executable)
            if executable_hash != self._expected_executable_sha256:
                return SpeechRecognitionHealth(
                    available=False,
                    provider="whisper.cpp",
                    model=str(self._model_path),
                    loaded=False,
                    detail="whisper.cpp executable integrity verification failed",
                )
        if self._expected_model_sha256:
            model_hash = await asyncio.to_thread(_sha256_file, self._model_path)
            if model_hash != self._expected_model_sha256:
                return SpeechRecognitionHealth(
                    available=False,
                    provider="whisper.cpp",
                    model=str(self._model_path),
                    loaded=False,
                    detail="local Whisper model integrity verification failed",
                )
        return SpeechRecognitionHealth(
            available=True,
            provider="whisper.cpp",
            model=str(self._model_path),
            loaded=self._loaded,
            detail=(
                "local whisper.cpp runtime is ready; integrity verified"
                if self.integrity_pinned
                else "local whisper.cpp runtime is ready"
            ),
        )

    async def transcribe(self, audio_bytes: bytes, mime: str) -> SpeechRecognitionResult:
        health = await self.health()
        if not health.available:
            raise SpeechRecognitionUnavailable(health.detail)
        if not audio_bytes:
            raise ValueError("audio is empty")
        if len(audio_bytes) > 50 * 1024 * 1024:
            raise ValueError("audio exceeds the bounded size limit")
        suffix = _audio_suffix(mime)
        descriptor, raw_path = tempfile.mkstemp(prefix="thoth-voice-", suffix=suffix)
        audio_path = Path(raw_path)
        started = time.perf_counter()
        deleted = False
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(audio_bytes)
            argv = [
                str(self._executable),
                "-m",
                str(self._model_path),
                "-f",
                str(audio_path),
                "-l",
                self._language,
                "--no-timestamps",
            ]
            self._loaded = True
            return_code, stdout, stderr = await self._runner(argv, audio_path)
            if return_code != 0:
                detail = _bounded_error(stderr)
                raise SpeechRecognitionUnavailable(
                    f"local whisper.cpp transcription failed: {detail}"
                )
            text = stdout.strip()
            if not text:
                raise SpeechRecognitionUnavailable("local whisper.cpp returned no transcript")
            completed_at = self._clock()
            transcript = FinalTranscript(
                text=text,
                confidence=0.0,
                language=self._language,
                duration_s=0.0,
                segments=(
                    TranscriptSegment(
                        text=text,
                        start_s=0,
                        end_s=0,
                        confidence=0.0,
                        final=True,
                    ),
                ),
                completed_at=completed_at,
            )
        finally:
            with contextlib.suppress(FileNotFoundError):
                await asyncio.to_thread(os.unlink, audio_path)
            deleted = True
        return SpeechRecognitionResult(
            transcript=transcript,
            provider="whisper.cpp",
            model=str(self._model_path),
            language=self._language,
            audio_deleted=deleted,
            elapsed_ms=(time.perf_counter() - started) * 1_000,
        )

    async def unload(self) -> None:
        self._loaded = False


class SpeechRecognitionSTTAdapter:
    """Compatibility adapter for the original one-shot voice endpoints."""

    def __init__(self, provider: SpeechRecognitionProvider) -> None:
        self._provider = provider

    async def transcribe(self, audio_bytes: bytes, mime: str) -> Transcript:
        result = await self._provider.transcribe(audio_bytes, mime)
        final = result.transcript
        return Transcript(
            text=final.text,
            confidence=final.confidence,
            duration_s=final.duration_s,
            language=final.language,
        )


def _audio_suffix(mime: str) -> str:
    normalized = mime.partition(";")[0].strip().lower()
    return {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/aiff": ".aiff",
        "audio/webm": ".webm",
        "audio/mp4": ".m4a",
    }.get(normalized, ".audio")


def _bounded_error(stderr: str) -> str:
    cleaned = " ".join(stderr.split())
    return cleaned[:512] or "unknown local runtime error"


def default_stt_adapter() -> STTAdapter:
    """Select local whisper.cpp by default; mocks require explicit opt-in."""
    selection = os.environ.get("THOTH_STT", "whisper.cpp")
    if selection == "mock":
        return MockSTTAdapter()
    if selection == "faster-whisper":
        return FasterWhisperSTTAdapter()
    provider = WhisperCppSpeechRecognitionProvider(
        executable=Path(
            os.environ.get("THOTH_WHISPER_EXECUTABLE", "/opt/homebrew/bin/whisper-cli")
        ),
        model_path=Path(
            os.environ.get(
                "THOTH_WHISPER_MODEL_PATH",
                "data/models/whisper/ggml-base.en.bin",
            )
        ),
        language=os.environ.get("THOTH_WHISPER_LANGUAGE", "en"),
        expected_executable_sha256=os.environ.get("THOTH_WHISPER_EXECUTABLE_SHA256"),
        expected_model_sha256=os.environ.get("THOTH_WHISPER_MODEL_SHA256"),
    )
    return SpeechRecognitionSTTAdapter(provider)
