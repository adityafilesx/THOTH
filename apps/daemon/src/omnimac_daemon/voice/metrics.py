"""Bounded in-memory latency instrumentation with no transcript content."""

from __future__ import annotations

import math
from collections import deque
from enum import StrEnum
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field


class VoiceLatencyStage(StrEnum):
    RECORDING_START = "recording_start"
    FIRST_PARTIAL = "first_partial"
    FINALISATION = "finalisation"
    REFLEX_ROUTE = "reflex_route"
    SKILL_ROUTE = "skill_route"
    PLANNER_VISIBLE = "planner_visible"
    TTS_INTERRUPTION = "tts_interruption"
    STOP_ACKNOWLEDGEMENT = "stop_acknowledgement"


class VoiceLatencySample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    count: int = Field(ge=1)
    p50_ms: float = Field(ge=0)
    p95_ms: float = Field(ge=0)
    last_ms: float = Field(ge=0)


class VoiceLatencySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stages: dict[VoiceLatencyStage, VoiceLatencySample]


class VoiceLatencyMetrics:
    """Process-local rolling samples; reset on restart and never persisted."""

    def __init__(self, *, max_samples_per_stage: int = 256) -> None:
        if max_samples_per_stage <= 0 or max_samples_per_stage > 10_000:
            raise ValueError("latency sample ceiling must be within 1-10000")
        self._maximum = max_samples_per_stage
        self._samples: dict[VoiceLatencyStage, deque[float]] = {}
        self._lock = Lock()

    def record(self, stage: VoiceLatencyStage, elapsed_ms: float) -> None:
        if elapsed_ms < 0:
            raise ValueError("voice latency must be non-negative")
        with self._lock:
            samples = self._samples.setdefault(stage, deque(maxlen=self._maximum))
            samples.append(float(elapsed_ms))

    def snapshot(self) -> VoiceLatencySnapshot:
        with self._lock:
            copied = {stage: tuple(values) for stage, values in self._samples.items() if values}
        return VoiceLatencySnapshot(
            stages={
                stage: VoiceLatencySample(
                    count=len(values),
                    p50_ms=_percentile(values, 0.50),
                    p95_ms=_percentile(values, 0.95),
                    last_ms=values[-1],
                )
                for stage, values in copied.items()
            }
        )


def _percentile(values: tuple[float, ...], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]
