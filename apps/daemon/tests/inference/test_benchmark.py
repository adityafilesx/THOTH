"""Hardware + model benchmark (Phase 5 slice 2).

The harness measures a provider over a fixed planning suite: schema-valid
%, tool-selection %, argument-extraction %, risk consistency (no
downgrades), scope consistency, plus timing. Scoring is pure and tested
with crafted plans; the real measurement is run by the CLI against the
live model to write docs/LOCAL_MODEL_EVALUATION.md.
"""

import pytest

from thoth_daemon.inference.benchmark import (
    BENCH_CASES,
    BenchCase,
    HardwareInfo,
    ModelBenchmark,
    benchmark_provider,
    detect_hardware,
    render_benchmark_markdown,
    score_plan,
)
from thoth_daemon.schemas import RiskLevel

RISK_FLOOR = {
    "fs_read_file": RiskLevel.R0,
    "fs_write_file": RiskLevel.R1,
    "git_status": RiskLevel.R0,
}


def _plan(*steps: dict) -> dict:
    return {"summary": "s", "steps": [{"index": i, **st} for i, st in enumerate(steps)]}


class TestHardwareDetection:
    def test_reports_real_values(self) -> None:
        hw = detect_hardware()
        assert hw.unified_memory_bytes > 0
        assert hw.cpu_cores > 0
        assert hw.chip  # non-empty brand string


class TestScorePlan:
    def _case(self, **kw) -> BenchCase:
        base = dict(
            name="c",
            goal="read a file",
            allowed_tools=["fs_read_file"],
            required_tools=["fs_read_file"],
            max_risk=RiskLevel.R1,
            expect_args={"fs_read_file": ["path"]},
        )
        base.update(kw)
        return BenchCase(**base)

    def test_perfect_plan_scores_all_true(self) -> None:
        plan = _plan(
            {"tool_name": "fs_read_file", "declared_risk": "R0", "arguments": {"path": "/x"}}
        )
        score = score_plan(plan, self._case(), RISK_FLOOR)
        assert score.schema_valid
        assert score.tool_selection_ok
        assert score.argument_extraction_ok
        assert score.risk_ok
        assert score.scope_ok

    def test_disallowed_tool_fails_selection(self) -> None:
        plan = _plan(
            {
                "tool_name": "fs_write_file",
                "declared_risk": "R1",
                "arguments": {"path": "/x", "content": "y"},
            }
        )
        score = score_plan(plan, self._case(), RISK_FLOOR)
        assert not score.tool_selection_ok

    def test_risk_downgrade_fails_risk(self) -> None:
        # fs_write_file default is R1; a plan declaring R0 is a downgrade.
        plan = _plan(
            {"tool_name": "fs_write_file", "declared_risk": "R0", "arguments": {"path": "/x"}}
        )
        case = self._case(
            allowed_tools=["fs_write_file"], required_tools=["fs_write_file"], expect_args={}
        )
        score = score_plan(plan, case, RISK_FLOOR)
        assert not score.risk_ok

    def test_missing_argument_fails_extraction(self) -> None:
        plan = _plan({"tool_name": "fs_read_file", "declared_risk": "R0", "arguments": {}})
        score = score_plan(plan, self._case(), RISK_FLOOR)
        assert not score.argument_extraction_ok

    def test_malformed_plan_fails_schema(self) -> None:
        assert not score_plan({"summary": "s"}, self._case(), RISK_FLOOR).schema_valid
        assert not score_plan({"summary": "s", "steps": []}, self._case(), RISK_FLOOR).schema_valid
        bad_risk = _plan({"tool_name": "fs_read_file", "declared_risk": "R9"})
        assert not score_plan(bad_risk, self._case(), RISK_FLOOR).schema_valid


class _FakeProvider:
    """Returns a fixed plan for every request; used to test aggregation."""

    def __init__(self, plan: dict, model_id: str = "fake") -> None:
        self._plan = plan
        self._model = model_id

    @property
    def name(self) -> str:
        return self._model

    async def warm_up(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    async def generate(self, request):
        import json

        from thoth_daemon.inference.base import InferenceResult

        return InferenceResult(
            text=json.dumps(self._plan),
            parsed=self._plan,
            model_id=self._model,
            tokens_out=len(json.dumps(self._plan).split()),
            duration_ms=5.0,
        )


class TestBenchmarkAggregation:
    async def test_all_pass_gives_full_scores(self) -> None:
        good = _plan(
            {"tool_name": "fs_read_file", "declared_risk": "R0", "arguments": {"path": "/x"}}
        )
        cases = [
            BenchCase(
                name="read",
                goal="read a file",
                allowed_tools=["fs_read_file"],
                required_tools=["fs_read_file"],
                max_risk=RiskLevel.R0,
                expect_args={"fs_read_file": ["path"]},
            )
        ]
        result = await benchmark_provider(
            _FakeProvider(good), cases, RISK_FLOOR, iterations=2, model_id="fake"
        )
        assert result.schema_valid_pct == 100.0
        assert result.tool_selection_pct == 100.0
        assert result.argument_extraction_pct == 100.0
        assert result.risk_consistency_pct == 100.0
        assert result.samples == 2

    async def test_bad_model_scores_low(self) -> None:
        bad = _plan({"tool_name": "made_up_tool", "declared_risk": "R0"})
        cases = [
            BenchCase(
                name="read",
                goal="read a file",
                allowed_tools=["fs_read_file"],
                required_tools=["fs_read_file"],
                max_risk=RiskLevel.R0,
                expect_args={},
            )
        ]
        result = await benchmark_provider(
            _FakeProvider(bad), cases, RISK_FLOOR, iterations=1, model_id="bad"
        )
        assert result.tool_selection_pct == 0.0


class TestReport:
    def test_render_names_models_and_hardware(self) -> None:
        hw = HardwareInfo(chip="Apple M4", cpu_cores=10, unified_memory_bytes=17_179_869_184)
        bench = ModelBenchmark(
            model_id="qwen3:4b",
            runtime="llama.cpp",
            samples=12,
            schema_valid_pct=100.0,
            tool_selection_pct=91.7,
            argument_extraction_pct=83.3,
            risk_consistency_pct=100.0,
            scope_consistency_pct=100.0,
            load_ms=800.0,
            ttft_ms=120.0,
            throughput_tok_s=45.0,
            peak_memory_bytes=3_000_000_000,
        )
        md = render_benchmark_markdown(hw, [bench], selected="qwen3:4b")
        assert "Apple M4" in md
        assert "qwen3:4b" in md
        assert "91.7" in md
        assert "Selected" in md

    def test_bench_cases_cover_the_risk_spectrum(self) -> None:
        assert len(BENCH_CASES) >= 8
        risks = {c.max_risk for c in BENCH_CASES}
        assert RiskLevel.R0 in risks and RiskLevel.R2 in risks


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
