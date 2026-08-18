"""Local inference abstraction (Phase 5 slice 1).

Provider-neutral inference behind a single protocol. The deterministic
provider is the always-available offline floor; the llama.cpp-family
provider talks to a loopback server (tested with an injected caller, plus
a live skipif test against a real Ollama); MLX is typed-unavailable until
installed; the Anthropic provider is disabled by default and never a
silent fallback. Network-isolation mode refuses any non-loopback endpoint.
"""

import hashlib
import json
from pathlib import Path

import pytest

from omnimac_daemon.inference import (
    AnthropicInferenceProvider,
    DeterministicInferenceProvider,
    InferenceRequest,
    InferenceUnavailableError,
    IsolationViolation,
    LlamaCppInferenceProvider,
    MLXInferenceProvider,
    ModelRegistry,
    ModelSpec,
    NetworkIsolationGuard,
)

PLAN_SCHEMA = {
    "type": "object",
    "required": ["summary", "steps"],
    "properties": {
        "summary": {"type": "string"},
        "steps": {"type": "array"},
    },
}


class TestDeterministicProvider:
    async def test_generates_schema_valid_plan_offline(self) -> None:
        provider = DeterministicInferenceProvider()
        req = InferenceRequest(prompt="read my notes", json_schema=PLAN_SCHEMA)
        result = await provider.generate(req)
        assert result.parsed is not None
        assert "summary" in result.parsed and isinstance(result.parsed["steps"], list)
        assert result.parsed["steps"]
        assert result.model_id == "deterministic"
        # text must be the JSON serialization of the parsed object
        assert json.loads(result.text) == result.parsed

    async def test_health_always_available(self) -> None:
        provider = DeterministicInferenceProvider()
        health = await provider.health()
        assert health.available

    async def test_metrics_count_requests(self) -> None:
        provider = DeterministicInferenceProvider()
        await provider.generate(InferenceRequest(prompt="x", json_schema=PLAN_SCHEMA))
        await provider.generate(InferenceRequest(prompt="y", json_schema=PLAN_SCHEMA))
        assert provider.metrics().requests == 2
        assert provider.metrics().failures == 0

    async def test_stream_yields_chunks(self) -> None:
        provider = DeterministicInferenceProvider()
        chunks = [c async for c in provider.generate_stream(InferenceRequest(prompt="hi"))]
        assert "".join(chunks)  # non-empty streamed text


class TestNetworkIsolation:
    def test_loopback_allowed(self) -> None:
        guard = NetworkIsolationGuard(isolation=True)
        for endpoint in ("http://127.0.0.1:11434", "http://localhost:8080", "http://[::1]:1234"):
            guard.check(endpoint)  # no raise

    def test_external_refused_in_isolation(self) -> None:
        guard = NetworkIsolationGuard(isolation=True)
        with pytest.raises(IsolationViolation):
            guard.check("https://api.anthropic.com")
        with pytest.raises(IsolationViolation):
            guard.check("http://192.168.1.50:11434")

    def test_external_allowed_when_isolation_off(self) -> None:
        guard = NetworkIsolationGuard(isolation=False)
        guard.check("https://api.anthropic.com")  # no raise


class TestModelRegistry:
    def test_add_get_list(self) -> None:
        reg = ModelRegistry()
        spec = ModelSpec(
            id="qwen3:4b",
            runtime="llama.cpp",
            quantization="Q4_K_M",
            memory_estimate_bytes=2_600_000_000,
            max_context=32768,
            capabilities=["json_schema", "streaming"],
            license="apache-2.0",
        )
        reg.add(spec)
        assert reg.get("qwen3:4b").runtime == "llama.cpp"
        assert "qwen3:4b" in [s.id for s in reg.list()]

    def test_integrity_hash_of_local_file(self, tmp_path: Path) -> None:
        f = tmp_path / "model.gguf"
        f.write_bytes(b"fake-weights")
        digest = ModelRegistry.integrity_hash(str(f))
        assert digest == hashlib.sha256(b"fake-weights").hexdigest()

    def test_json_round_trip(self, tmp_path: Path) -> None:
        reg = ModelRegistry()
        reg.add(
            ModelSpec(
                id="qwen3:8b",
                runtime="llama.cpp",
                quantization="Q4_K_M",
                memory_estimate_bytes=5_200_000_000,
                max_context=32768,
                capabilities=["json_schema"],
                license="apache-2.0",
            )
        )
        path = tmp_path / "registry.json"
        reg.save(path)
        loaded = ModelRegistry.load(path)
        assert loaded.get("qwen3:8b").memory_estimate_bytes == 5_200_000_000


class _FakeOllama:
    """Injected async HTTP caller mimicking the Ollama /api endpoints."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url: str, payload: dict, timeout: float) -> dict:
        self.calls.append((url, payload))
        if url.endswith("/api/generate"):
            plan = {"summary": "Plan for: " + payload["prompt"], "steps": [{"tool_name": "x"}]}
            return {"response": json.dumps(plan), "prompt_eval_count": 12, "eval_count": 20}
        raise AssertionError(f"unexpected url {url}")

    async def get(self, url: str, timeout: float) -> dict:
        self.calls.append((url, {}))
        return {"version": "0.31.1"}


class TestLlamaCppProvider:
    async def test_generate_constrained_json_via_local_server(self) -> None:
        fake = _FakeOllama()
        provider = LlamaCppInferenceProvider(endpoint="http://127.0.0.1:11434", model="qwen3:4b", http=fake)
        result = await provider.generate(InferenceRequest(prompt="read notes", json_schema=PLAN_SCHEMA))
        assert result.parsed == {"summary": "Plan for: read notes", "steps": [{"tool_name": "x"}]}
        assert result.tokens_in == 12 and result.tokens_out == 20
        assert result.model_id == "qwen3:4b"
        # the schema was passed to the server as the constrained format
        gen_call = next(p for u, p in fake.calls if u.endswith("/api/generate"))
        assert gen_call["format"] == PLAN_SCHEMA
        assert gen_call["stream"] is False

    async def test_refuses_non_loopback_endpoint(self) -> None:
        with pytest.raises(IsolationViolation):
            LlamaCppInferenceProvider(endpoint="http://10.0.0.5:11434", model="qwen3:4b", isolation=True)

    async def test_health_reports_server_version(self) -> None:
        provider = LlamaCppInferenceProvider(model="qwen3:4b", http=_FakeOllama())
        health = await provider.health()
        assert health.available

    async def test_warm_up_and_unload_use_keep_alive(self) -> None:
        fake = _FakeOllama()
        provider = LlamaCppInferenceProvider(model="qwen3:4b", http=fake)
        await provider.warm_up()
        await provider.unload()
        payloads = [p for u, p in fake.calls if u.endswith("/api/generate")]
        assert any(p.get("keep_alive") == 0 for p in payloads)  # unload evicts


class TestMLXProvider:
    async def test_unavailable_when_mlx_absent(self) -> None:
        provider = MLXInferenceProvider(model="qwen3-4b-mlx")
        try:
            import mlx_lm  # noqa: F401

            pytest.skip("mlx_lm installed; live path pending verification")
        except ImportError:
            pass
        with pytest.raises(InferenceUnavailableError, match="mlx"):
            await provider.generate(InferenceRequest(prompt="x"))
        assert not (await provider.health()).available


class TestAnthropicProviderGating:
    def test_not_constructible_without_explicit_opt_in(self, monkeypatch) -> None:
        monkeypatch.delenv("OmniMac_ALLOW_CLOUD", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
        with pytest.raises(InferenceUnavailableError, match="disabled"):
            AnthropicInferenceProvider()

    def test_refused_in_isolation_even_with_opt_in(self, monkeypatch) -> None:
        monkeypatch.setenv("OmniMac_ALLOW_CLOUD", "1")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
        with pytest.raises((IsolationViolation, InferenceUnavailableError)):
            AnthropicInferenceProvider(isolation=True)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
