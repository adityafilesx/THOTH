from __future__ import annotations

from typing import Any

from thoth_daemon.voice.stop import GlobalStopAuthority


class _Sessions:
    def __init__(self) -> None:
        self.calls = 0

    def cancel_all(self) -> int:
        self.calls += 1
        return 2


class _TTS:
    def __init__(self) -> None:
        self.calls = 0

    async def interrupt(self) -> bool:
        self.calls += 1
        return True


class _Orchestrator:
    def __init__(self) -> None:
        self.calls = 0

    async def cancel_all(self) -> tuple[list[Any], set[str]]:
        self.calls += 1
        return [object(), object(), object()], {"approval-1"}


async def test_global_stop_cancels_every_layer_without_model_or_router() -> None:
    sessions = _Sessions()
    tts = _TTS()
    orchestrator = _Orchestrator()
    authority = GlobalStopAuthority(
        sessions=sessions,
        tts=tts,
        orchestrator=orchestrator,
    )

    result = await authority.stop(reason="voice_phrase")

    assert result.reason == "voice_phrase"
    assert result.voice_sessions_cancelled == 2
    assert result.speech_interrupted is True
    assert result.tasks_cancelled == 3
    assert result.approvals_invalidated == 1
    assert sessions.calls == tts.calls == orchestrator.calls == 1


async def test_global_stop_is_safe_when_every_layer_is_idle() -> None:
    class IdleSessions:
        def cancel_all(self) -> int:
            return 0

    class IdleTTS:
        async def interrupt(self) -> bool:
            return False

    class IdleOrchestrator:
        async def cancel_all(self) -> tuple[list[Any], set[str]]:
            return [], set()

    result = await GlobalStopAuthority(
        sessions=IdleSessions(),
        tts=IdleTTS(),
        orchestrator=IdleOrchestrator(),
    ).stop(reason="escape")
    assert result.tasks_cancelled == 0
    assert result.approvals_invalidated == 0
    assert result.speech_interrupted is False
