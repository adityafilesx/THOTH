"""Deterministic emergency stop phrase matching."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class _SessionCanceller(Protocol):
    def cancel_all(self) -> int: ...


class _SpeechInterruptor(Protocol):
    async def interrupt(self) -> bool: ...


class _TaskCanceller(Protocol):
    async def cancel_all(self) -> tuple[Sequence[object], set[str]]: ...


class GlobalStopResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str = Field(min_length=1, max_length=64)
    voice_sessions_cancelled: int = Field(ge=0)
    speech_interrupted: bool
    tasks_cancelled: int = Field(ge=0)
    approvals_invalidated: int = Field(ge=0)


class GlobalStopAuthority:
    """Single model-free authority for emergency cancellation."""

    def __init__(
        self,
        *,
        sessions: _SessionCanceller,
        tts: _SpeechInterruptor,
        orchestrator: _TaskCanceller,
    ) -> None:
        self._sessions = sessions
        self._tts = tts
        self._orchestrator = orchestrator

    async def stop(self, *, reason: str) -> GlobalStopResult:
        voice_sessions = self._sessions.cancel_all()
        speech, cancellation = await asyncio.gather(
            self._tts.interrupt(),
            self._orchestrator.cancel_all(),
        )
        tasks, invalidated = cancellation
        return GlobalStopResult(
            reason=reason,
            voice_sessions_cancelled=voice_sessions,
            speech_interrupted=speech,
            tasks_cancelled=len(tasks),
            approvals_invalidated=len(invalidated),
        )


class StopPhraseDetector:
    """Match only an explicit, whole push-to-talk utterance.

    Matching is deliberately independent of inference, skills, planning, and
    external content. TTS feedback is never eligible.
    """

    _PHRASES = frozenset({"thoth stop", "stop thoth"})

    def matches(
        self,
        text: str,
        *,
        push_to_talk_active: bool,
        tts_playing: bool,
    ) -> bool:
        if not push_to_talk_active or tts_playing:
            return False
        normalized = unicodedata.normalize("NFKC", text).casefold()
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
        return normalized in self._PHRASES
