"""Interruptible text-to-speech over macOS ``say`` (Phase 4 slice 6).

Real subprocess (argv-only, no shell), injectable command for hermetic
tests. Interruptible by contract: ``interrupt()`` terminates the current
utterance (SIGTERM, SIGKILL fallback) and a new ``speak()`` while
speaking interrupts the previous utterance first. Spoken text is not
logged above DEBUG.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from thoth_daemon.core.persona import SpokenResponse
from thoth_daemon.voice.contracts import (
    SpeechPlayback,
    SpeechPlaybackState,
    SpeechRequest,
    SpeechSegment,
    SpeechSynthesisHealth,
    SpeechSynthesisProvider,
)

if TYPE_CHECKING:
    from thoth_daemon.core.local_runtime import LocalAIRuntimeManager

logger = logging.getLogger(__name__)

Command = Callable[[str], list[str]]


def _default_command(text: str) -> list[str]:
    return ["say", text]


class SpeechHandle:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process

    async def wait(self) -> int:
        return await self._process.wait()

    @property
    def running(self) -> bool:
        return self._process.returncode is None


class TTSSpeaker:
    def __init__(self, command: Command | None = None) -> None:
        self._command = command or _default_command
        self._current: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    @property
    def is_speaking(self) -> bool:
        return self._current is not None and self._current.returncode is None

    async def speak(self, text: str) -> SpeechHandle:
        async with self._lock:
            if self.is_speaking:
                await self._terminate_locked()
            logger.debug("tts speaking %d chars", len(text))
            argv = self._command(text)
            self._current = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return SpeechHandle(self._current)

    async def interrupt(self) -> bool:
        async with self._lock:
            if not self.is_speaking:
                return False
            await self._terminate_locked()
            return True

    async def _terminate_locked(self) -> None:
        process = self._current
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=0.15)
        except TimeoutError:
            process.kill()
            with contextlib.suppress(ProcessLookupError):
                await process.wait()


class SpeechSynthesisUnavailable(RuntimeError):
    """The selected local speech provider cannot run."""


SegmentCommand = Callable[[SpeechSegment, SpeechRequest], list[str]]


class _TaskSpeechHandle:
    def __init__(self, task: asyncio.Task[int]) -> None:
        self._task = task

    async def wait(self) -> int:
        return await self._task

    @property
    def running(self) -> bool:
        return not self._task.done()


_CUE_SOUNDS = {
    "confirmation": "/System/Library/Sounds/Glass.aiff",
    "attention": "/System/Library/Sounds/Ping.aiff",
    "failure": "/System/Library/Sounds/Basso.aiff",
}


def _macos_command(segment: SpeechSegment, request: SpeechRequest) -> list[str]:
    if segment.cue is not None:
        return ["/usr/bin/afplay", _CUE_SOUNDS[segment.cue]]
    argv = ["/usr/bin/say"]
    if request.voice is not None:
        argv.extend(["-v", request.voice.identifier])
    argv.extend(["-r", str(request.rate_wpm), segment.text])
    return argv


class MacOSSpeechSynthesisProvider:
    """Segmented local playback through macOS ``say`` and system cue files."""

    def __init__(self, command: SegmentCommand = _macos_command) -> None:
        self._command = command
        self._state = SpeechPlaybackState.IDLE
        self._task: asyncio.Task[int] | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> SpeechPlaybackState:
        return self._state

    async def health(self) -> SpeechSynthesisHealth:
        available = await asyncio.to_thread(os.path.isfile, "/usr/bin/say")
        return SpeechSynthesisHealth(
            available=available,
            provider="macos-say",
            detail="macOS local speech is ready" if available else "macOS say is unavailable",
        )

    async def speak(self, request: SpeechRequest) -> SpeechPlayback:
        await self.interrupt()
        async with self._lock:
            self._state = SpeechPlaybackState.SPEAKING
            self._task = asyncio.create_task(self._play(request))
            return _TaskSpeechHandle(self._task)

    async def interrupt(self) -> bool:
        async with self._lock:
            task = self._task
            process = self._process
            if task is None or task.done():
                return False
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.15)
                except TimeoutError:
                    process.kill()
                    with contextlib.suppress(ProcessLookupError):
                        await process.wait()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            self._state = SpeechPlaybackState.INTERRUPTED
            return True

    async def _play(self, request: SpeechRequest) -> int:
        return_code = 0
        try:
            for segment in request.segments:
                argv = self._command(segment, request)
                self._process = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                return_code = await self._process.wait()
                if return_code != 0:
                    self._state = SpeechPlaybackState.FAILED
                    return return_code
                if segment.pause_after_ms:
                    await asyncio.sleep(segment.pause_after_ms / 1_000)
            self._state = SpeechPlaybackState.IDLE
            return return_code
        except asyncio.CancelledError:
            raise
        except Exception:
            self._state = SpeechPlaybackState.FAILED
            raise
        finally:
            self._process = None


class PiperSpeechSynthesisProvider:
    """Optional fully local Piper renderer with interruptible ``afplay``."""

    def __init__(
        self,
        *,
        executable: Path = Path("/opt/homebrew/bin/piper"),
        model_path: Path = Path("data/models/piper/voice.onnx"),
        player: Path = Path("/usr/bin/afplay"),
    ) -> None:
        self._executable = executable
        self._model_path = model_path
        self._player = player
        self._state = SpeechPlaybackState.IDLE
        self._task: asyncio.Task[int] | None = None
        self._process: asyncio.subprocess.Process | None = None

    @property
    def state(self) -> SpeechPlaybackState:
        return self._state

    async def health(self) -> SpeechSynthesisHealth:
        executable_exists = await asyncio.to_thread(self._executable.is_file)
        model_exists = await asyncio.to_thread(self._model_path.is_file)
        player_exists = await asyncio.to_thread(self._player.is_file)
        if not executable_exists or not os.access(self._executable, os.X_OK):
            return SpeechSynthesisHealth(
                available=False,
                provider="piper",
                detail="Piper executable is unavailable",
            )
        if not model_exists:
            return SpeechSynthesisHealth(
                available=False,
                provider="piper",
                detail="Piper voice model is unavailable",
            )
        if not player_exists:
            return SpeechSynthesisHealth(
                available=False,
                provider="piper",
                detail="local audio player is unavailable",
            )
        return SpeechSynthesisHealth(
            available=True,
            provider="piper",
            voice=self._model_path.name,
            detail="local Piper speech is ready",
        )

    async def speak(self, request: SpeechRequest) -> SpeechPlayback:
        health = await self.health()
        if not health.available:
            raise SpeechSynthesisUnavailable(health.detail)
        await self.interrupt()
        self._state = SpeechPlaybackState.SPEAKING
        self._task = asyncio.create_task(self._render_and_play(request))
        return _TaskSpeechHandle(self._task)

    async def interrupt(self) -> bool:
        task = self._task
        if task is None or task.done():
            return False
        process = self._process
        if process is not None and process.returncode is None:
            process.terminate()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=0.15)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._state = SpeechPlaybackState.INTERRUPTED
        return True

    async def _render_and_play(self, request: SpeechRequest) -> int:
        descriptor, raw_path = tempfile.mkstemp(prefix="thoth-piper-", suffix=".wav")
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        output = Path(raw_path)
        text = " ".join(segment.text for segment in request.segments if segment.text)
        try:
            length_scale = 185 / request.rate_wpm
            self._process = await asyncio.create_subprocess_exec(
                str(self._executable),
                "--model",
                str(self._model_path),
                "--output_file",
                str(output),
                "--length_scale",
                f"{length_scale:.3f}",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await self._process.communicate(text.encode("utf-8"))
            if self._process.returncode != 0:
                self._state = SpeechPlaybackState.FAILED
                return int(self._process.returncode or 1)
            self._process = await asyncio.create_subprocess_exec(
                str(self._player),
                str(output),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return_code = await self._process.wait()
            self._state = (
                SpeechPlaybackState.IDLE if return_code == 0 else SpeechPlaybackState.FAILED
            )
            return return_code
        finally:
            self._process = None
            with contextlib.suppress(FileNotFoundError):
                await asyncio.to_thread(os.unlink, output)


_SENSITIVE_SPEECH = re.compile(
    r"(/Users/|~/?\.ssh|\b(password|secret|token|authorization|credential|passphrase)\b)",
    re.IGNORECASE,
)


class SpeechSynthesisService:
    """Speak only persona-bounded output through a local provider."""

    def __init__(
        self,
        provider: SpeechSynthesisProvider,
        *,
        rate_wpm: int = 185,
        runtime: LocalAIRuntimeManager | None = None,
    ) -> None:
        self._provider = provider
        self._rate_wpm = rate_wpm
        self._runtime = runtime
        self._managed_task: asyncio.Task[int] | None = None

    def bind_runtime(self, runtime: LocalAIRuntimeManager) -> None:
        self._runtime = runtime

    async def speak(self, response: SpokenResponse) -> SpeechPlayback | None:
        text = response.text.strip()
        if not text:
            return None
        if len(text) > response.max_chars:
            text = text[: response.max_chars - 1].rstrip() + "…"
        if _SENSITIVE_SPEECH.search(text):
            text = "Sensitive details are available in the display."
        request = SpeechRequest(
            segments=(SpeechSegment(text=text),),
            rate_wpm=self._rate_wpm,
        )
        return await self._speak(request)

    async def cue(
        self,
        cue: Literal["confirmation", "attention", "failure"] = "confirmation",
    ) -> SpeechPlayback:
        segment = SpeechSegment(cue=cue)
        return await self._speak(SpeechRequest(segments=(segment,)))

    async def interrupt(self) -> bool:
        interrupted = await self._provider.interrupt()
        task = self._managed_task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            interrupted = True
        return interrupted

    async def _speak(self, request: SpeechRequest) -> SpeechPlayback:
        if self._runtime is None:
            return await self._provider.speak(request)
        self._managed_task = asyncio.create_task(self._managed_playback(request))
        return _TaskSpeechHandle(self._managed_task)

    async def _managed_playback(self, request: SpeechRequest) -> int:
        from thoth_daemon.core.local_runtime import RuntimeComponent

        if self._runtime is None:  # guarded by _speak; keeps narrowing explicit
            raise RuntimeError("local runtime manager is not bound")
        async with self._runtime.use(RuntimeComponent.TEXT_TO_SPEECH):
            handle = await self._provider.speak(request)
            return await handle.wait()
