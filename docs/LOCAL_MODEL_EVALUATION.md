# Local model evaluation (Phase 5.0 slice 2)

Hardware: **Apple M4**, 10 cores, 17 GB unified memory.

**Selected default model: `qwen3:4b`** (chosen by measured schema-valid % first, then latency within the memory budget).

| model | runtime | samples | schema-valid% | tool-sel% | arg-extr% | risk-consistent% | scope% | load ms | tok/s |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|
| deterministic | deterministic | 20 | 100.0 | 20.0 | 80.0 | 100.0 | 40.0 | 0.0 | 0.0 |
| qwen3:4b | llama.cpp | 20 | 100.0 | 100.0 | 50.0 | 90.0 | 100.0 | 2054.0 | 30.3 |
| qwen3:8b | llama.cpp | 20 | 100.0 | 100.0 | 30.0 | 90.0 | 100.0 | 3620.7 | 13.3 |
| qwen3 (MLX) | mlx | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

- `qwen3 (MLX)`: SKIPPED: mlx_lm not installed (MLX comparison unavailable)

## Metric definitions

- **schema-valid%** — plans that parse and match the plan contract (summary + typed steps with a valid risk).
- **tool-sel%** — required tool present AND every tool within the approved set.
- **arg-extr%** — every expected argument key present and non-empty.
- **risk-consistent%** — no step declares a risk BELOW the tool's default (a downgrade *attempt*; the validator rejects it regardless).
- **scope%** — no step references a tool outside the approved set (a scope-expansion attempt; over-declaring risk is safe and does not count here).

## Reading these numbers

Every metric is a measure of how often the model gets it right on its own. NONE of them is a safety boundary: unknown tools, extra arguments, risk downgrades, and scope expansion are ALL rejected deterministically by the plan validator and the unchanged Phase 4 gates (registry, policy, scope, approvals, verifiers) before anything executes. A lower arg-extraction score means more clarification requests or plan rejections, never an unsafe action.
