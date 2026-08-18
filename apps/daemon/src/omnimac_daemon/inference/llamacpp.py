"""llama.cpp-family inference provider (Phase 5 slice 1).

Talks to a LOOPBACK llama.cpp-family server (Ollama-compatible: POST
/api/generate with format=<json-schema> for constrained decoding, GET
/api/version for health, keep_alive for warm/unload). The HTTP caller is
injected so the provider unit-tests offline; a real Ollama round-trip is a
separate live test. When the in-process `llama_cpp` package is present it
could bind directly — kept behind the same contract — but the server path
is the one present and verifiable on the target machine.

The endpoint is validated by the NetworkIsolationGuard at construction and
per request: it must be loopback.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any, Protocol

from omnimac_daemon.inference.base import (
    InferenceError,
    InferenceRequest,
    InferenceResult,
    ProviderHealth,
    _MetricsMixin,
)
from omnimac_daemon.inference.isolation import NetworkIsolationGuard

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"


class HttpCaller(Protocol):
    async def post(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]: ...
    async def get(self, url: str, timeout: float) -> dict[str, Any]: ...


class _UrllibCaller:
    """Minimal stdlib HTTP caller (no third-party dependency). Runs the
    blocking request in a thread so the event loop is never blocked."""

    async def post(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        import asyncio

        return await asyncio.to_thread(self._request, url, payload, timeout)

    async def get(self, url: str, timeout: float) -> dict[str, Any]:
        import asyncio

        return await asyncio.to_thread(self._request, url, None, timeout)

    @staticmethod
    def _request(url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
        import urllib.request

        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(  # noqa: S310 - loopback only, guard-checked
            url, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return dict(json.loads(resp.read().decode()))


class LlamaCppInferenceProvider(_MetricsMixin):
    def __init__(
        self,
        model: str = "qwen3:4b",
        endpoint: str = DEFAULT_ENDPOINT,
        http: HttpCaller | None = None,
        isolation: bool = False,
    ) -> None:
        super().__init__()
        self._guard = NetworkIsolationGuard(isolation=isolation)
        self._guard.check(endpoint)  # refuse non-loopback at construction
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._http = http or _UrllibCaller()

    @property
    def name(self) -> str:
        return "llama.cpp"

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        self._guard.check(self._endpoint)
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": request.prompt,
            "system": request.system,
            "stream": False,
            "think": request.think,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        if request.json_schema is not None:
            payload["format"] = request.json_schema  # server-side constrained decoding
        started = time.perf_counter()
        try:
            body = await self._http.post(f"{self._endpoint}/api/generate", payload, request.timeout_s)
        except Exception as exc:
            self._record((time.perf_counter() - started) * 1000, 0, ok=False)
            raise InferenceError(f"local inference request failed: {exc}") from exc
        duration_ms = (time.perf_counter() - started) * 1000
        text = str(body.get("response", ""))
        parsed: dict[str, Any] | None = None
        if request.json_schema is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                self._record(duration_ms, 0, ok=False)
                raise InferenceError(f"model did not return valid JSON: {exc}") from exc
        tokens_out = int(body.get("eval_count", 0))
        self._record(duration_ms, tokens_out, ok=True)
        return InferenceResult(
            text=text,
            parsed=parsed,
            model_id=self._model,
            tokens_in=int(body.get("prompt_eval_count", 0)),
            tokens_out=tokens_out,
            duration_ms=duration_ms,
        )

    async def generate_stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        # The offline test path uses the non-streaming call; a real streaming
        # implementation reads NDJSON chunks. Kept simple and correct here.
        result = await self.generate(request)
        yield result.text

    async def warm_up(self) -> None:
        self._guard.check(self._endpoint)
        await self._http.post(
            f"{self._endpoint}/api/generate",
            {"model": self._model, "prompt": "", "keep_alive": "10m"},
            30.0,
        )

    async def unload(self) -> None:
        self._guard.check(self._endpoint)
        await self._http.post(
            f"{self._endpoint}/api/generate",
            {"model": self._model, "prompt": "", "keep_alive": 0},
            30.0,
        )

    async def health(self) -> ProviderHealth:
        try:
            self._guard.check(self._endpoint)
            body = await self._http.get(f"{self._endpoint}/api/version", 5.0)
        except Exception as exc:
            return ProviderHealth(available=False, detail=str(exc), model_id=self._model)
        return ProviderHealth(available=True, detail=f"server {body.get('version', '?')}", model_id=self._model)
