# Phase 5 gap report, slice plan, and risk register

**Date:** 2026-07-13 · Audit of the Phase 4 repository (main @ `29860a8`, 607 tests green) against the Phase 5 "Local-First Embodiment" specification.

## 1. Environment audit (measured, not assumed)

| Item | Found |
|---|---|
| Chip | Apple **M4**, 10 cores |
| Unified memory | **16 GB** (17179869184 bytes) |
| `llama_cpp` (python) | absent |
| `mlx_lm` / `mlx` | absent |
| **Ollama** (llama.cpp-family local server) | **installed AND running** (v0.31.1, `127.0.0.1:11434`), zero models pulled |
| `anthropic` SDK | present (cloud — optional, disabled by default in Phase 5) |
| faster-whisper / whisper.cpp / piper | absent |
| `/usr/bin/say` | present (Phase 4 TTS verified) |

Consequences: a REAL local-inference path is verifiable in this session via Ollama after pulling a quantized model (Qwen3-4B ≈ 2.6 GB; Qwen3-8B q4 ≈ 5.2 GB — both fit 16 GB). MLX comparison requires installing `mlx_lm` (possible; benchmark plan covers it). STT/Piper remain pending live verification as in Phase 4.

## 2. Per-requirement gap audit

| Phase 5 requirement | Phase 4 state | Gap |
|---|---|---|
| Local LLM inference | none — only `ClaudePlanner` (cloud, unverified) + mock planner | **Full build** (slice 1): provider protocol, llama.cpp-family/MLX/deterministic/optional-Anthropic providers, model registry, isolation mode |
| Hardware/model benchmark | none | **Full build** (slice 2): detection is real now; model benchmarks run against Ollama-pulled Qwen3 variants |
| Reflex / skill / local-reasoning routing | none — every `POST /api/tasks` goal goes to the configured planner | **Full build** (slice 3): deterministic intent router in front of `Orchestrator.submit`, no LLM on the reflex path |
| Local constrained planner | plan validation exists (schema, registry, policy, scope, 25-step cap) | **Partial**: add `LocalPlanner(PlannerAdapter)` over the provider with schema-constrained decoding + a strict `PlanValidator` (unknown tools/args/workspaces, risk-floor, verifier requirements) and the skill→clarify→fail-safe fallback ladder |
| Persona layer | none (raw task JSON to UI) | Full build (slice 5) — post-verification composition only |
| Foreground context broker / app profiles | app launch/focus + AX adapter exist | Slices 6–7 |
| Menu-bar / overlay / palette / HUD | seven desktop views exist; none of these four surfaces | Slice 8 |
| Fully local STT / TTS | adapters exist (mock STT default; `say` TTS verified) | Slices 9–10 (whisper.cpp, Piper) |
| Interruption matrix | cancel + TTS interrupt exist; no Escape/double-Escape/global bindings, no per-state matrix | Slice 11 |
| Dialogue state / workspace intelligence / resource manager / resumable tasks / proactivity / Demonstration-to-Draft / dogfood | none | Slices 12–18 |
| Safety boundaries | complete (Phase 4) | **Preserved untouched** — Phase 5 adds layers in front of/behind them, never through them |

## 3. Phase gating (this instruction)

- **Phase 5.0 = slices 1–2** (local inference abstraction; hardware + model benchmark). Acceptance: provider contract fully unit-tested; deterministic provider passes the planner-eval suite; real Ollama round-trip with schema-valid JSON; benchmark harness produces `docs/LOCAL_MODEL_EVALUATION.md` from measured runs; network-isolation mode provably blocks non-local hosts.
- **Phase 5.1 = slices 3–4** (reflex/hybrid intent router; local constrained planner). Acceptance: reflex commands never construct a provider call (asserted); skill path deterministic after input binding; local planner output validated by the strict validator with every rejection class tested; fallback ladder (skill → clarification → fail safe) tested; zero silent cloud fallback (asserted).
- Voice, proactivity, and all later slices **do not start** until both gates pass.

## 4. Slice plan (5.0 + 5.1 detail)

1. **Slice 1 — inference abstraction** (`omnimac_daemon/inference/`): `InferenceProvider` protocol (`generate(request) -> InferenceResult`, `generate_stream`, `warm_up`, `unload`, `health`, `metrics`; request carries prompt/system/schema/max_tokens/timeout/cancellation token); `DeterministicInferenceProvider` (keyword-routed, offline); `LlamaCppInferenceProvider` (llama.cpp family: in-process `llama_cpp` when installed, else the local llama.cpp server API at `127.0.0.1` — Ollama-compatible `/api/generate` with `format=<json-schema>`; streaming; `keep_alive` for warm/unload); `MLXInferenceProvider` (lazy `mlx_lm`, typed unavailable); `AnthropicInferenceProvider` (**disabled unless `OmniMac_ALLOW_CLOUD=1` AND key present**); `ModelRegistry` (id, path/ref, runtime, quantization, memory estimate, max context, capabilities, benchmark results, license, integrity hash); `NetworkIsolationGuard` — in isolation mode any provider whose endpoint is not loopback/in-process is refused.
2. **Slice 2 — benchmark** (`omnimac_daemon/inference/benchmark.py` + `evals/run_local_bench.py`): hardware detection (chip generation, unified memory) real; per-model measurements (load, TTFT, tok/s, peak RSS delta, schema-valid %, tool selection, argument extraction, risk/scope consistency over a fixed prompt suite); candidates Qwen3-4B + Qwen3-8B (quantized) via Ollama; MLX comparison recorded as unavailable unless installed; writes `docs/LOCAL_MODEL_EVALUATION.md`; default model chosen from measurements.
3. **Slice 3 — intent router** (`omnimac_daemon/core/intent_router.py`): tiered resolution — REFLEX (exact/deterministic patterns: stop, cancel, status, open/focus <approved app>, run <skill>, continue <workspace>, mute/interrupt; **no provider object even constructed**), SKILL (name/alias + typed-input extraction), PLANNER (everything else). Router returns a typed `RoutedIntent`; execution still flows through the existing orchestrator/policy pipeline unchanged.
4. **Slice 4 — local constrained planner**: `LocalPlanner(PlannerAdapter)` = provider + `PLAN_SCHEMA`-constrained decoding + `PlanValidator` (unknown tool, unknown/extra argument names vs tool input models, unknown workspace/app references, step/limit caps, risk floor = tool default (no downgrade emitted), required verification checks for effectful tools). Failure ladder: matching skill → `ClarificationNeeded` → fail safe. Cloud fallback structurally impossible in local mode (test asserts no Anthropic provider is constructed).

Slices 5–20 as specified; scheduled after the two gates.

## 5. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | 16 GB M4: Qwen3-8B + daemon + desktop under memory pressure | M | M | benchmark measures peak memory; registry stores estimates; resource manager (slice 14) evicts; default model chosen by measurement |
| R2 | Local model emits schema-invalid or malicious plans | H | H | constrained decoding + strict `PlanValidator` + ALL Phase 4 gates (registry/policy/scope/approvals/verifiers) unchanged; rejection classes each tested |
| R3 | Silent cloud fallback | L | H | Anthropic provider disabled by default; local mode never constructs it (asserted in tests); isolation guard refuses non-loopback endpoints |
| R4 | Reflex path accidentally routes through LLM | M | H | router tests assert zero provider construction/calls on reflex inputs, incl. injection-styled inputs |
| R5 | Ollama server absent/crashed at runtime | M | M | health checks; typed `InferenceUnavailableError`; fallback ladder ends in fail-safe, never cloud |
| R6 | Benchmark numbers unrepresentative (thermal, background load) | M | L | record conditions; multiple iterations; report medians; energy/thermal noted where obtainable |
| R7 | Model downloads (2.6–5.2 GB) fail/slow | M | L | benchmark harness treats missing models as SKIPPED with reason; report stays honest |
| R8 | Persona layer drifts into altering facts | L | H | composer consumes only verified typed results; unit tests assert no mutation of inputs (slice 5, gated later) |
| R9 | Prompt injection via transcript/web text reaching the router | M | H | router treats input as opaque text for exact-match reflex only; planner path inherits injection guard; tests include hostile phrasings |
| R10 | Scope creep past 5.1 before gates | M | M | this document’s gating section; STATUS tracks gate state |

## 6. Claim ceiling (recorded now)

Until every Phase 5 gate passes, no claim beyond Phase 4's. After all gates: “OmniMac is a local-first personal computer intelligence that understands natural voice and text commands, safely operates supported applications, executes and verifies multi-step workflows, maintains short-term operational context, and functions without a cloud language model.”
