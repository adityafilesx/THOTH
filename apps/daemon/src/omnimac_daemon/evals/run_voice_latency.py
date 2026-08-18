"""Measure deterministic Phase 5.5 latency stages without a microphone/model."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime

from omnimac_daemon.core.intent_router import IntentRouter
from omnimac_daemon.voice.contracts import (
    AudioCaptureMode,
    FinalTranscript,
    SpeechRequest,
    SpeechSegment,
)
from omnimac_daemon.voice.service import VoiceSessionRegistry
from omnimac_daemon.voice.stop import GlobalStopAuthority
from omnimac_daemon.voice.stt import MockSpeechRecognitionProvider
from omnimac_daemon.voice.tts import MacOSSpeechSynthesisProvider


def _summary(samples: list[float]) -> dict[str, float | int]:
    ordered = sorted(samples)

    def percentile(value: float) -> float:
        index = max(0, min(len(ordered) - 1, int(len(ordered) * value + 0.999999) - 1))
        return round(ordered[index], 3)

    return {"samples": len(samples), "p50_ms": percentile(0.50), "p95_ms": percentile(0.95)}


def _measure_sync(operation: Callable[[], object], iterations: int) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1_000)
    return samples


async def _main() -> None:
    now = datetime.now(UTC)
    provider = MockSpeechRecognitionProvider(
        FinalTranscript(
            text="stop",
            confidence=1,
            language="en",
            duration_s=0,
            completed_at=now,
        )
    )

    def recording_start() -> None:
        registry = VoiceSessionRegistry(provider)
        snapshot = registry.start(AudioCaptureMode.HOLD)
        registry.cancel(snapshot.session_id)

    router = IntentRouter(
        known_apps={"TextEdit"},
        known_skills={"project-health"},
        known_workspaces={"OmniMac"},
    )

    class _Sessions:
        def cancel_all(self) -> int:
            return 0

    class _TTS:
        async def interrupt(self) -> bool:
            return False

    class _Tasks:
        async def cancel_all(self) -> tuple[list[object], set[str]]:
            return [], set()

    stop = GlobalStopAuthority(sessions=_Sessions(), tts=_TTS(), orchestrator=_Tasks())
    stop_samples: list[float] = []
    for _ in range(500):
        started = time.perf_counter()
        await stop.stop(reason="benchmark")
        stop_samples.append((time.perf_counter() - started) * 1_000)

    interrupt_samples: list[float] = []
    tts = MacOSSpeechSynthesisProvider(
        command=lambda segment, request: [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ]
    )
    for _ in range(25):
        await tts.speak(SpeechRequest(segments=(SpeechSegment(text="benchmark"),)))
        await asyncio.sleep(0.005)
        started = time.perf_counter()
        await tts.interrupt()
        interrupt_samples.append((time.perf_counter() - started) * 1_000)

    result = {
        "recording_start": _summary(_measure_sync(recording_start, 1_000)),
        "reflex_route": _summary(_measure_sync(lambda: router.route("Omnimac, stop."), 10_000)),
        "skill_route": _summary(_measure_sync(lambda: router.route("run project-health"), 10_000)),
        "tts_interruption": _summary(interrupt_samples),
        "stop_acknowledgement": _summary(stop_samples),
        "first_partial": {"available": False, "reason": "whisper.cpp model unavailable"},
        "finalisation": {"available": False, "reason": "whisper.cpp model unavailable"},
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
