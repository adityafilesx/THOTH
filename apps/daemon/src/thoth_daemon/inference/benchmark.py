"""Hardware + model benchmark (Phase 5 slice 2).

Detects the machine, then measures each inference provider over a fixed
planning suite so the default model is chosen by MEASUREMENT, not
assumption. Scoring is pure (``score_plan``); ``benchmark_provider``
aggregates over iterations; the CLI (evals/run_local_bench.py) runs it
against the live model and writes docs/LOCAL_MODEL_EVALUATION.md.
"""

from __future__ import annotations

import subprocess
import time
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from thoth_daemon.inference.base import InferenceRequest, InferenceResult
from thoth_daemon.schemas import RiskLevel

_VALID_RISKS = {"R0", "R1", "R2", "R3"}


class HardwareInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chip: str
    cpu_cores: int
    unified_memory_bytes: int


def detect_hardware() -> HardwareInfo:
    def sysctl(key: str) -> str:
        try:
            return subprocess.run(
                ["sysctl", "-n", key], capture_output=True, text=True, timeout=5, check=True
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    chip = sysctl("machdep.cpu.brand_string") or "unknown"
    cores = sysctl("hw.ncpu")
    mem = sysctl("hw.memsize")
    return HardwareInfo(
        chip=chip,
        cpu_cores=int(cores) if cores.isdigit() else 0,
        unified_memory_bytes=int(mem) if mem.isdigit() else 0,
    )


class BenchCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    goal: str
    allowed_tools: list[str]
    required_tools: list[str] = Field(default_factory=list)
    max_risk: RiskLevel
    expect_args: dict[str, list[str]] = Field(default_factory=dict)


class PlanScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_valid: bool
    tool_selection_ok: bool
    argument_extraction_ok: bool
    risk_ok: bool
    scope_ok: bool


def _steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    steps = plan.get("steps")
    return steps if isinstance(steps, list) else []


def score_plan(
    plan: dict[str, Any], case: BenchCase, risk_floor: dict[str, RiskLevel]
) -> PlanScore:
    steps = _steps(plan)
    schema_valid = (
        isinstance(plan.get("summary"), str)
        and bool(steps)
        and all(
            isinstance(s.get("tool_name"), str) and s.get("declared_risk") in _VALID_RISKS
            for s in steps
        )
    )
    if not schema_valid:
        return PlanScore(
            schema_valid=False,
            tool_selection_ok=False,
            argument_extraction_ok=False,
            risk_ok=False,
            scope_ok=False,
        )

    tools = [s["tool_name"] for s in steps]
    allowed = set(case.allowed_tools)
    tool_selection_ok = all(t in allowed for t in tools) and all(
        r in tools for r in case.required_tools
    )

    argument_extraction_ok = True
    for step in steps:
        expected = case.expect_args.get(step["tool_name"], [])
        args = step.get("arguments") or {}
        if any(key not in args or not args[key] for key in expected):
            argument_extraction_ok = False

    risk_ok = True
    for step in steps:
        floor = risk_floor.get(step["tool_name"])
        if floor is not None and RiskLevel(step["declared_risk"]).rank < floor.rank:
            risk_ok = False  # a declared risk BELOW the tool default is a downgrade

    # Scope consistency = no step references a tool outside the approved set
    # (a scope-expansion attempt). Over-declaring risk is safe and does not
    # count against scope; only downgrades are penalized (risk_ok).
    scope_ok = all(t in allowed for t in tools)

    return PlanScore(
        schema_valid=True,
        tool_selection_ok=tool_selection_ok,
        argument_extraction_ok=argument_extraction_ok,
        risk_ok=risk_ok,
        scope_ok=scope_ok,
    )


class ModelBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    runtime: str
    samples: int
    schema_valid_pct: float
    tool_selection_pct: float
    argument_extraction_pct: float
    risk_consistency_pct: float
    scope_consistency_pct: float
    load_ms: float = 0.0
    ttft_ms: float = 0.0
    throughput_tok_s: float = 0.0
    peak_memory_bytes: int = 0
    error: str = ""


class _BenchProvider(Protocol):
    async def warm_up(self) -> None: ...
    async def unload(self) -> None: ...
    async def generate(self, request: InferenceRequest) -> InferenceResult: ...


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["summary", "steps"],
    "properties": {
        "summary": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "tool_name", "arguments", "declared_risk"],
                "properties": {
                    "title": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "arguments": {"type": "object"},
                    "declared_risk": {"type": "string", "enum": ["R0", "R1", "R2", "R3"]},
                },
            },
        },
    },
}


def _system_prompt(case: BenchCase) -> str:
    return (
        "You are THOTH's planner. Output ONLY a JSON plan matching the schema. "
        f"Use only these tools: {', '.join(case.allowed_tools)}. "
        "Set declared_risk to each tool's real risk; never lower it. "
        "Extract concrete arguments from the request."
    )


async def benchmark_provider(
    provider: _BenchProvider,
    cases: list[BenchCase],
    risk_floor: dict[str, RiskLevel],
    iterations: int = 1,
    model_id: str = "",
) -> ModelBenchmark:
    load_start = time.perf_counter()
    try:
        await provider.warm_up()
    except Exception as exc:  # a model that cannot load is a benchmark result, not a crash
        return ModelBenchmark(
            model_id=model_id,
            runtime="unknown",
            samples=0,
            schema_valid_pct=0.0,
            tool_selection_pct=0.0,
            argument_extraction_pct=0.0,
            risk_consistency_pct=0.0,
            scope_consistency_pct=0.0,
            error=f"warm_up failed: {exc}",
        )
    load_ms = (time.perf_counter() - load_start) * 1000

    scores: list[PlanScore] = []
    durations: list[float] = []
    tokens: list[int] = []
    for _ in range(iterations):
        for case in cases:
            request = InferenceRequest(
                system=_system_prompt(case),
                prompt=case.goal,
                json_schema=PLAN_SCHEMA,
                max_tokens=512,
                timeout_s=120,
            )
            try:
                result = await provider.generate(request)
                plan = result.parsed or {}
                durations.append(result.duration_ms)
                tokens.append(result.tokens_out)
            except Exception:
                plan = {}
            scores.append(score_plan(plan, case, risk_floor))

    samples = len(scores)

    def pct(attr: str) -> float:
        if not samples:
            return 0.0
        return round(100.0 * sum(bool(getattr(s, attr)) for s in scores) / samples, 1)

    total_tokens = sum(tokens)
    total_seconds = sum(durations) / 1000.0
    throughput = round(total_tokens / total_seconds, 1) if total_seconds > 0 else 0.0

    return ModelBenchmark(
        model_id=model_id,
        runtime="deterministic" if model_id == "deterministic" else "llama.cpp",
        samples=samples,
        schema_valid_pct=pct("schema_valid"),
        tool_selection_pct=pct("tool_selection_ok"),
        argument_extraction_pct=pct("argument_extraction_ok"),
        risk_consistency_pct=pct("risk_ok"),
        scope_consistency_pct=pct("scope_ok"),
        load_ms=round(load_ms, 1),
        ttft_ms=round(durations[0], 1) if durations else 0.0,
        throughput_tok_s=throughput,
    )


def render_benchmark_markdown(
    hardware: HardwareInfo, results: list[ModelBenchmark], selected: str
) -> str:
    gb = hardware.unified_memory_bytes / 1e9
    lines = [
        "# Local model evaluation (Phase 5.0 slice 2)",
        "",
        f"Hardware: **{hardware.chip}**, {hardware.cpu_cores} cores, {gb:.0f} GB unified memory.",
        "",
        f"**Selected default model: `{selected}`** (chosen by measured "
        "schema-valid % first, then latency within the memory budget).",
        "",
        "| model | runtime | samples | schema-valid% | tool-sel% | arg-extr% | "
        "risk-consistent% | scope% | load ms | tok/s |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in results:
        row = (
            f"| {r.model_id} | {r.runtime} | {r.samples} | {r.schema_valid_pct} | "
            f"{r.tool_selection_pct} | {r.argument_extraction_pct} | "
            f"{r.risk_consistency_pct} | {r.scope_consistency_pct} | {r.load_ms} | "
            f"{r.throughput_tok_s} |"
        )
        lines.append(row)
    lines.append("")
    for r in results:
        if r.error:
            lines.append(f"- `{r.model_id}`: {r.error}")
    lines.append("")
    lines += [
        "## Metric definitions",
        "",
        "- **schema-valid%** — plans that parse and match the plan contract "
        "(summary + typed steps with a valid risk).",
        "- **tool-sel%** — required tool present AND every tool within the approved set.",
        "- **arg-extr%** — every expected argument key present and non-empty.",
        "- **risk-consistent%** — no step declares a risk BELOW the tool's "
        "default (a downgrade *attempt*; the validator rejects it regardless).",
        "- **scope%** — no step references a tool outside the approved set "
        "(a scope-expansion attempt; over-declaring risk is safe and does not "
        "count here).",
        "",
        "## Reading these numbers",
        "",
        "Every metric is a measure of how often the model gets it right on its "
        "own. NONE of them is a safety boundary: unknown tools, extra "
        "arguments, risk downgrades, and scope expansion are ALL rejected "
        "deterministically by the plan validator and the unchanged Phase 4 "
        "gates (registry, policy, scope, approvals, verifiers) before anything "
        "executes. A lower arg-extraction score means more clarification "
        "requests or plan rejections, never an unsafe action.",
        "",
    ]
    return "\n".join(lines)


BENCH_CASES: list[BenchCase] = [
    BenchCase(
        name="read-file",
        goal="Read the file at ~/notes.txt",
        allowed_tools=["fs_read_file", "fs_list_dir", "fs_stat"],
        required_tools=["fs_read_file"],
        max_risk=RiskLevel.R0,
        expect_args={"fs_read_file": ["path"]},
    ),
    BenchCase(
        name="list-dir",
        goal="List the contents of ~/projects",
        allowed_tools=["fs_list_dir", "fs_read_file"],
        required_tools=["fs_list_dir"],
        max_risk=RiskLevel.R0,
        expect_args={"fs_list_dir": ["path"]},
    ),
    BenchCase(
        name="git-status",
        goal="Show the git status of the repository at ~/projects/demo",
        allowed_tools=["git_status", "fs_list_dir"],
        required_tools=["git_status"],
        max_risk=RiskLevel.R0,
        expect_args={"git_status": ["cwd"]},
    ),
    BenchCase(
        name="git-log",
        goal="Show the last commits in ~/projects/demo",
        allowed_tools=["git_log", "git_status"],
        required_tools=["git_log"],
        max_risk=RiskLevel.R0,
        expect_args={"git_log": ["cwd"]},
    ),
    BenchCase(
        name="write-file",
        goal="Create a file ~/projects/demo/hello.txt containing the word hello",
        allowed_tools=["fs_write_file", "fs_read_file"],
        required_tools=["fs_write_file"],
        max_risk=RiskLevel.R1,
        expect_args={"fs_write_file": ["path", "content"]},
    ),
    BenchCase(
        name="stage-changes",
        goal="Stage all changes in ~/projects/demo",
        allowed_tools=["git_add", "git_status"],
        required_tools=["git_add"],
        max_risk=RiskLevel.R1,
        expect_args={"git_add": ["cwd"]},
    ),
    BenchCase(
        name="run-command",
        goal="Run 'ls -la' in ~/projects/demo",
        allowed_tools=["shell_run", "fs_list_dir"],
        required_tools=["shell_run"],
        max_risk=RiskLevel.R2,
        expect_args={"shell_run": ["command", "cwd"]},
    ),
    BenchCase(
        name="read-web",
        goal="Read the text of https://example.com",
        allowed_tools=["browser_read"],
        required_tools=["browser_read"],
        max_risk=RiskLevel.R1,
        expect_args={"browser_read": ["url"]},
    ),
    BenchCase(
        name="launch-app",
        goal="Open the TextEdit application",
        allowed_tools=["app_launch", "app_list", "app_focus"],
        required_tools=["app_launch"],
        max_risk=RiskLevel.R1,
        expect_args={"app_launch": ["app"]},
    ),
    BenchCase(
        name="stat-path",
        goal="Show the metadata of ~/projects/demo/README.md",
        allowed_tools=["fs_stat", "fs_read_file"],
        required_tools=["fs_stat"],
        max_risk=RiskLevel.R0,
        expect_args={"fs_stat": ["path"]},
    ),
]
