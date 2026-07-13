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
from collections.abc import Callable

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
