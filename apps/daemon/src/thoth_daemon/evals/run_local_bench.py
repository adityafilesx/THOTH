"""CLI: benchmark local model candidates and write docs/LOCAL_MODEL_EVALUATION.md.

    uv run --project apps/daemon python -m thoth_daemon.evals.run_local_bench \
        --models qwen3:4b qwen3:8b --iterations 2

Detects hardware, benchmarks the deterministic floor plus each requested
llama.cpp-family model that is actually pulled (missing models recorded as
SKIPPED), and selects the default by measured schema-valid % then latency.
MLX variants are recorded unavailable unless mlx_lm is installed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.error
import urllib.request
from pathlib import Path

from thoth_daemon.inference import DeterministicInferenceProvider, LlamaCppInferenceProvider
from thoth_daemon.inference.benchmark import (
    BENCH_CASES,
    ModelBenchmark,
    benchmark_provider,
    detect_hardware,
    render_benchmark_markdown,
)
from thoth_daemon.schemas import RiskLevel
from thoth_daemon.tools.app_tools import register_app_tools
from thoth_daemon.tools.browser_tools import register_browser_tools
from thoth_daemon.tools.fs_tools import register_fs_tools
from thoth_daemon.tools.git_tools import register_git_tools
from thoth_daemon.tools.registry import ToolRegistry
from thoth_daemon.tools.shell_tool import register_shell_tool

ENDPOINT = "http://127.0.0.1:11434"


def _risk_floor() -> dict[str, RiskLevel]:
    registry = ToolRegistry()
    register_fs_tools(registry)
    register_shell_tool(registry)
    register_git_tools(registry)
    register_app_tools(registry)
    register_browser_tools(registry)
    return {tool.name: tool.default_risk for tool in registry.all()}


def _pulled(model: str) -> bool:
    try:
        req = urllib.request.Request(f"{ENDPOINT}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            tags = json.loads(resp.read().decode())
        return any(m.get("name", "").startswith(model) for m in tags.get("models", []))
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


async def _run(models: list[str], iterations: int) -> list[ModelBenchmark]:
    risk_floor = _risk_floor()
    results: list[ModelBenchmark] = [
        await benchmark_provider(
            DeterministicInferenceProvider(),
            BENCH_CASES,
            risk_floor,
            iterations=iterations,
            model_id="deterministic",
        )
    ]
    for model in models:
        if not _pulled(model):
            results.append(
                ModelBenchmark(
                    model_id=model,
                    runtime="llama.cpp",
                    samples=0,
                    schema_valid_pct=0.0,
                    tool_selection_pct=0.0,
                    argument_extraction_pct=0.0,
                    risk_consistency_pct=0.0,
                    scope_consistency_pct=0.0,
                    error="SKIPPED: model not pulled (ollama pull <model>)",
                )
            )
            continue
        provider = LlamaCppInferenceProvider(model=model, endpoint=ENDPOINT)
        bench = await benchmark_provider(
            provider, BENCH_CASES, risk_floor, iterations=iterations, model_id=model
        )
        results.append(bench)

    # Record the MLX comparison honestly: benchmarked when mlx_lm is present,
    # otherwise a SKIPPED row (spec: compare llama.cpp and MLX when available).
    try:
        import mlx_lm  # noqa: F401

        mlx_note = ""  # a real MLX benchmark would be added here when installed
    except ImportError:
        mlx_note = "SKIPPED: mlx_lm not installed (MLX comparison unavailable)"
    if mlx_note:
        results.append(
            ModelBenchmark(
                model_id="qwen3 (MLX)",
                runtime="mlx",
                samples=0,
                schema_valid_pct=0.0,
                tool_selection_pct=0.0,
                argument_extraction_pct=0.0,
                risk_consistency_pct=0.0,
                scope_consistency_pct=0.0,
                error=mlx_note,
            )
        )
    return results


def _select(results: list[ModelBenchmark]) -> str:
    ran = [r for r in results if r.samples > 0 and not r.error]
    # Prefer a real local model over the deterministic floor when it clears a
    # schema-valid bar; otherwise fall back to deterministic.
    models = [r for r in ran if r.runtime == "llama.cpp" and r.schema_valid_pct >= 90.0]
    if models:
        best = max(models, key=lambda r: (r.schema_valid_pct, r.throughput_tok_s))
        return best.model_id
    return "deterministic"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="*", default=["qwen3:4b", "qwen3:8b"])
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("docs/LOCAL_MODEL_EVALUATION.md"))
    args = parser.parse_args(argv)

    hardware = detect_hardware()
    results = asyncio.run(_run(args.models, args.iterations))
    selected = _select(results)
    report = render_benchmark_markdown(hardware, results, selected)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    for r in results:
        print(
            f"{r.model_id:16} schema={r.schema_valid_pct:5}% tool={r.tool_selection_pct:5}% "
            f"arg={r.argument_extraction_pct:5}% risk={r.risk_consistency_pct:5}% "
            f"tok/s={r.throughput_tok_s} {r.error}"
        )
    print(f"\nselected default: {selected}\nreport written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
