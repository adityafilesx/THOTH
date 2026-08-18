"""Optional Anthropic inference provider (Phase 5 slice 1).

DISABLED BY DEFAULT. Constructed only when OmniMac_ALLOW_CLOUD=1 AND an API
key is present, and NEVER while network isolation is on. It is never part
of the fallback ladder — local inference failing routes to a deterministic
skill, a clarification request, or a safe failure, never to the cloud.
This exists so a user can explicitly opt in; the application runs fully
without it.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from omnimac_daemon.inference.base import (
    InferenceRequest,
    InferenceResult,
    InferenceUnavailableError,
    ProviderHealth,
    _MetricsMixin,
)
from omnimac_daemon.inference.isolation import IsolationViolation

ANTHROPIC_ENDPOINT = "https://api.anthropic.com"


class AnthropicInferenceProvider(_MetricsMixin):
    def __init__(self, model: str = "claude-opus-4-8", isolation: bool = False) -> None:
        super().__init__()
        if isolation:
            raise IsolationViolation("cloud inference is refused while network isolation is on")
        if os.environ.get("OMNIMAC_ALLOW_CLOUD") != "1":
            raise InferenceUnavailableError(
                "cloud inference is disabled by default; set OMNIMAC_ALLOW_CLOUD=1 to opt-in to Anthropic API usage. Requires network connectivity."
            )
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise InferenceUnavailableError("OMNIMAC_ALLOW_CLOUD is set but ANTHROPIC_API_KEY is not")
        self._model = model

    @property
    def name(self) -> str:
        return "anthropic"

    async def generate(self, request: InferenceRequest) -> InferenceResult:  # pragma: no cover
        raise InferenceUnavailableError("cloud generation is intentionally not wired into the local planner path")

    async def generate_stream(self, request: InferenceRequest) -> AsyncIterator[str]:  # pragma: no cover
        raise InferenceUnavailableError("cloud streaming not wired")
        yield ""

    async def warm_up(self) -> None:  # pragma: no cover
        return None

    async def unload(self) -> None:  # pragma: no cover
        return None

    async def health(self) -> ProviderHealth:  # pragma: no cover
        return ProviderHealth(available=False, detail="cloud disabled by default")
