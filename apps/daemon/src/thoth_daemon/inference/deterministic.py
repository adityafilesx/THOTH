"""Deterministic inference provider (Phase 5 slice 1).

The always-available offline floor: keyword-routed plan generation that
requires NO model, NO network, and NO API key. Used as the fail-safe when
every model backend is unavailable, and as a stable baseline for the
provider contract and planner-eval suite. Produces JSON that satisfies a
requested plan schema (summary + steps)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from thoth_daemon.inference.base import (
    InferenceRequest,
    InferenceResult,
    ProviderHealth,
    _MetricsMixin,
)

# Minimal keyword → (summary tag, steps) routing. Steps use real tool names
# so downstream validation (slice 4) has something valid to accept; risk is
# never emitted below a tool's default (the validator enforces the floor).
_ROUTES: list[tuple[tuple[str, ...], list[dict[str, object]]]] = [
    (
        ("read", "show", "open file", "notes"),
        [{"title": "Read a file", "tool_name": "fs_read_file", "declared_risk": "R0"}],
    ),
    (
        ("status", "git status", "health"),
        [{"title": "Git status", "tool_name": "git_status", "declared_risk": "R0"}],
    ),
    (
        ("list", "directory", "workspace"),
        [{"title": "List a directory", "tool_name": "fs_list_dir", "declared_risk": "R0"}],
    ),
]

_FALLBACK: list[dict[str, object]] = [
    {"title": "List the current directory", "tool_name": "fs_list_dir", "declared_risk": "R0"}
]


class DeterministicInferenceProvider(_MetricsMixin):
    def __init__(self) -> None:
        super().__init__()

    @property
    def name(self) -> str:
        return "deterministic"

    def _plan(self, prompt: str) -> dict[str, object]:
        lowered = prompt.lower()
        steps = next(
            (steps for keys, steps in _ROUTES if any(k in lowered for k in keys)),
            _FALLBACK,
        )
        indexed = [{"index": i, **step} for i, step in enumerate(steps)]
        return {"summary": f"Plan for: {prompt}", "steps": indexed}

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        plan = self._plan(request.prompt)
        text = json.dumps(plan)
        parsed = plan if request.json_schema is not None else None
        self._record(duration_ms=0.0, tokens_out=len(text.split()), ok=True)
        return InferenceResult(
            text=text,
            parsed=parsed,
            model_id="deterministic",
            tokens_in=len(request.prompt.split()),
            tokens_out=len(text.split()),
        )

    async def generate_stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        result = await self.generate(request)
        for token in result.text.split(" "):
            yield token + " "

    async def warm_up(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    async def health(self) -> ProviderHealth:
        return ProviderHealth(available=True, detail="deterministic", model_id="deterministic")
