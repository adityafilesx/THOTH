"""Provider-neutral local inference contract (Phase 5 slice 1).

Consumed ONLY by planning / argument-extraction layers — never by tools,
policy, approvals, or verification. Every provider is cancellable and
timeout-bounded; a caller never hangs on inference.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class InferenceError(Exception):
    """Inference failed (server error, parse failure, timeout)."""


class InferenceUnavailableError(InferenceError):
    """The backend is not installed/enabled in this environment."""


class InferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    prompt: str
    system: str = ""
    json_schema: dict[str, Any] | None = None  # constrained decoding when set
    max_tokens: int = 1024
    timeout_s: float = 60.0
    temperature: float = 0.0
    # Thinking models (Qwen3) burn the token budget on <think> before the
    # answer; constrained planning wants the structured answer directly.
    think: bool = False
    cancellation: asyncio.Event | None = Field(default=None, exclude=True)


class InferenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    parsed: dict[str, Any] | None = None
    model_id: str
    tokens_in: int = 0
    tokens_out: int = 0
    ttft_ms: float = 0.0
    duration_ms: float = 0.0


class ProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    detail: str = ""
    model_id: str | None = None


class ProviderMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests: int = 0
    failures: int = 0
    tokens_out: int = 0
    p50_ms: float = 0.0
    p95_ms: float = 0.0


@runtime_checkable
class InferenceProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def generate(self, request: InferenceRequest) -> InferenceResult: ...
    def generate_stream(self, request: InferenceRequest) -> AsyncIterator[str]: ...
    async def warm_up(self) -> None: ...
    async def unload(self) -> None: ...
    async def health(self) -> ProviderHealth: ...
    def metrics(self) -> ProviderMetrics: ...


class _MetricsMixin:
    """Shared latency/request bookkeeping for concrete providers."""

    def __init__(self) -> None:
        self._requests = 0
        self._failures = 0
        self._tokens_out = 0
        self._latencies: list[float] = []

    def _record(self, duration_ms: float, tokens_out: int, ok: bool) -> None:
        self._requests += 1
        self._tokens_out += tokens_out
        if not ok:
            self._failures += 1
        self._latencies.append(duration_ms)

    def metrics(self) -> ProviderMetrics:
        latencies = sorted(self._latencies)

        def pct(p: float) -> float:
            if not latencies:
                return 0.0
            idx = min(len(latencies) - 1, int(p * len(latencies)))
            return latencies[idx]

        return ProviderMetrics(
            requests=self._requests,
            failures=self._failures,
            tokens_out=self._tokens_out,
            p50_ms=pct(0.5),
            p95_ms=pct(0.95),
        )
