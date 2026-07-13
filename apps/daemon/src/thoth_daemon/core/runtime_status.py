"""Local runtime status boundary (Phase 5.2 slice 3).

The minimal status/health surface persona and the UI need — NOT the full
LocalAIRuntimeManager (deferred). Persona reports degraded operation
honestly: any non-ready runtime maps to the DEGRADED_MODE intent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from thoth_daemon.core.persona import ResponseIntent
from thoth_daemon.inference.base import ProviderHealth


class LocalRuntimeStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    STARTING = "starting"
    READY = "ready"
    GENERATING = "generating"
    DEGRADED = "degraded"
    FAILED = "failed"

    def persona_intent(self) -> ResponseIntent | None:
        """The honest persona intent for a non-ready runtime, else None."""
        if self in (
            LocalRuntimeStatus.UNAVAILABLE,
            LocalRuntimeStatus.DEGRADED,
            LocalRuntimeStatus.FAILED,
        ):
            return ResponseIntent.DEGRADED_MODE
        return None


class _HealthProvider(Protocol):
    async def health(self) -> ProviderHealth: ...


class LocalRuntimeMonitor:
    def __init__(self, provider: _HealthProvider) -> None:
        self._provider = provider

    async def status(self) -> LocalRuntimeStatus:
        try:
            health = await self._provider.health()
        except Exception:
            return LocalRuntimeStatus.FAILED
        return LocalRuntimeStatus.READY if health.available else LocalRuntimeStatus.UNAVAILABLE
