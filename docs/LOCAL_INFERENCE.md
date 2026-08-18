# Local inference — decision record and architecture (Phase 5.0)

**Date:** 2026-07-13 · Status: Accepted (ADR-027 summarizes this in DECISIONS.md)

## Decision

Local inference sits behind a provider-neutral `InferenceProvider` protocol in `omnimac_daemon/inference/`, consumed ONLY by planning/argument-extraction layers (never by tools, policy, approvals, or verification). Four providers:

| Provider | Transport | Status on this machine |
|---|---|---|
| `DeterministicInferenceProvider` | in-process rules | always available; the fail-safe floor |
| `LlamaCppInferenceProvider` | in-process `llama_cpp` when installed, else the **local llama.cpp-family server API** on `127.0.0.1` (Ollama-compatible: `/api/generate`, `format=<json-schema>`, `keep_alive`) | **verifiable now** — Ollama 0.31.1 is installed and running with no models pulled yet |
| `MLXInferenceProvider` | lazy `mlx_lm` in-process | typed-unavailable until installed; benchmarked when present |
| `AnthropicInferenceProvider` | HTTPS (cloud) | **disabled by default**; constructed only when `OmniMac_ALLOW_CLOUD=1` AND a key exists; never a silent fallback |

Why llama.cpp-family-over-local-server first: it is the only runtime PRESENT on the target machine (measured, not assumed), it already provides quantized model management, schema-constrained generation, streaming, warm/unload (`keep_alive`), and it binds to loopback. In-process `llama_cpp` support is implemented behind the same provider so nothing changes if the user prefers no server. MLX is compared in the benchmark when installed (M-series advantage is plausible but must be measured — spec: "measured performance, not assumption").

## Provider contract

`InferenceRequest`: system, prompt, json_schema (optional — constrained decoding), max_tokens, timeout_s, temperature, cancellation event.
`InferenceResult`: text, parsed (when schema), tokens_in/out, ttft_ms, duration_ms, model_id.
Every provider implements: `generate`, `generate_stream` (chunk iterator), `warm_up`, `unload`, `health() -> ProviderHealth`, `metrics() -> ProviderMetrics` (requests, failures, tokens, p50/p95 latency). Timeouts and cancellation enforced in the provider; callers never hang.

## Network isolation mode

`OmniMac_NETWORK_ISOLATION=1` (or Settings flag): `NetworkIsolationGuard.check(endpoint)` refuses any endpoint that is not loopback (`127.0.0.1`, `::1`, `localhost`) or in-process. The Anthropic provider is refused outright in isolation mode regardless of flags. Guard is enforced at provider construction and per request, and external browser reads/navigation are now rejected before adapter invocation. Local files, subprocess tools, app control, reflex/skills, and loopback services remain available.

## Model registry

`ModelRegistry` (JSON file under the daemon data dir, Pydantic-validated): model id, local path or runtime ref, runtime (`llama.cpp` | `mlx` | `deterministic`), quantization, memory estimate (bytes), max context, capabilities (json_schema, streaming, tools), benchmark results (filled by slice 2), license string, integrity hash (sha256 of the model file when a local path exists; runtime-reported digest otherwise). Models never auto-execute remote code; registry entries are data only.

## Failure ladder (no silent cloud)

1. Matching deterministic skill → run it.
2. Otherwise → typed `ClarificationNeeded` back to the user.
3. Otherwise → fail safely (task FAILED with reason; audit records `planner.error`).
Cloud never enters this ladder. In local mode the Anthropic provider class is not even constructed (tested).

## Hardware benchmark plan (slice 2 — executes before default-model selection)

1. Detect chip (`sysctl machdep.cpu.brand_string`) and unified memory (`hw.memsize`) — real values recorded (M4, 16 GB).
2. Candidates when hardware permits (16 GB does): `qwen3:4b` and `qwen3:8b` quantized via Ollama; MLX variants when `mlx_lm` installed (else recorded SKIPPED with reason).
3. Per candidate, over a fixed 12-case planning suite (reusing planner-eval expectations): model load time, time-to-first-token, generation throughput (tok/s), peak memory delta (RSS + `ollama ps` size), **schema-valid plan %**, correct tool selection %, correct argument extraction %, risk consistency (no downgrades emitted), scope consistency (no out-of-scope paths/domains), energy/thermal notes where `pmset -g therm` yields data.
4. Medians over ≥3 iterations; conditions recorded (power, load).
5. Results + the selected default written to `docs/LOCAL_MODEL_EVALUATION.md`; the registry stores per-model results. Selection is by measurement (schema-valid % first, then latency within memory budget).
