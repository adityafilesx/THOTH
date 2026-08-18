"""Sync local-planner client over the loopback llama.cpp-family server.

Implements ``LocalPlanClient.complete_plan`` with a synchronous urllib
call so ``LocalPlanner`` stays a sync ``PlannerAdapter`` (matching
ClaudePlanner's design). Endpoint is loopback and guard-checked;
constrained decoding is requested via the JSON schema; thinking is
disabled so the token budget goes to the structured answer.
"""

from __future__ import annotations

import json
from typing import Any

from omnimac_daemon.inference.isolation import NetworkIsolationGuard

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"


class OllamaPlanClient:
    def __init__(
        self,
        model: str = "qwen3:4b",
        endpoint: str = DEFAULT_ENDPOINT,
        isolation: bool = False,
        timeout_s: float = 120.0,
    ) -> None:
        self._guard = NetworkIsolationGuard(isolation=isolation)
        self._guard.check(endpoint)
        self._endpoint = endpoint.rstrip("/")
        self._model = model
        self._timeout = timeout_s

    def complete_plan(self, system: str, goal: str, schema: dict[str, Any]) -> dict[str, Any]:
        import urllib.request

        self._guard.check(self._endpoint)
        payload = {
            "model": self._model,
            "system": system,
            "prompt": goal,
            "stream": False,
            "think": False,
            "format": schema,
            "options": {"temperature": 0.0, "num_predict": 1024},
        }
        req = urllib.request.Request(  # noqa: S310 - loopback, guard-checked
            f"{self._endpoint}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
            body = json.loads(resp.read().decode())
        text = str(body.get("response", ""))
        return dict(json.loads(text))
