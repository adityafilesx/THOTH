"""LIVE local-inference round-trip (Phase 5 slice 1).

Exercises the REAL llama.cpp-family server (Ollama on 127.0.0.1) with a
pulled quantized model, proving constrained JSON generation end-to-end.
Skips cleanly when the server is down or the model is not pulled, so the
offline suite is unaffected.
"""

import json
import urllib.error
import urllib.request

import pytest

from omnimac_daemon.inference import InferenceRequest, LlamaCppInferenceProvider

ENDPOINT = "http://127.0.0.1:11434"
MODEL = "qwen3:4b"

PLAN_SCHEMA = {
    "type": "object",
    "required": ["summary", "steps"],
    "properties": {
        "summary": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "tool_name", "declared_risk"],
                "properties": {
                    "title": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "declared_risk": {"type": "string", "enum": ["R0", "R1", "R2", "R3"]},
                },
            },
        },
    },
}


def _model_available() -> bool:
    try:
        req = urllib.request.Request(f"{ENDPOINT}/api/tags", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            tags = json.loads(resp.read().decode())
        return any(m.get("name", "").startswith(MODEL) for m in tags.get("models", []))
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


pytestmark = pytest.mark.skipif(not _model_available(), reason=f"{MODEL} not pulled / Ollama not running")


async def test_live_constrained_json_plan() -> None:
    provider = LlamaCppInferenceProvider(model=MODEL, endpoint=ENDPOINT)
    assert (await provider.health()).available
    result = await provider.generate(
        InferenceRequest(
            system=(
                "You are OmniMac's planner. Output ONLY a JSON plan matching the schema. "
                "Use tool_name 'fs_read_file' for reading a file, declared_risk 'R0'."
            ),
            prompt="Read the file at ~/notes.txt",
            json_schema=PLAN_SCHEMA,
            max_tokens=512,
            timeout_s=120,
        )
    )
    assert result.parsed is not None, result.text
    assert isinstance(result.parsed["summary"], str)
    assert result.parsed["steps"], "expected at least one step"
    assert result.tokens_out > 0
    assert result.model_id == MODEL


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
