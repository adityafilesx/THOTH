from thoth_daemon.core.verification import VerificationEngine
from thoth_daemon.schemas import (
    PlanStep,
    RiskLevel,
    ToolResult,
    VerificationStrategy,
)

engine = VerificationEngine()


def step(strategy_tool: str = "mock_read_file") -> PlanStep:
    return PlanStep(
        index=0,
        title="t",
        tool_name=strategy_tool,
        arguments={},
        declared_risk=RiskLevel.R0,
    )


def ok_result() -> ToolResult:
    return ToolResult(invocation_id="i1", ok=True, output={"lines": 3})


def fail_result() -> ToolResult:
    return ToolResult(invocation_id="i1", ok=False, error="boom")


class TestVerification:
    def test_output_assertion_passes_on_ok_result(self) -> None:
        vr = engine.verify(step(), ok_result(), VerificationStrategy.OUTPUT_ASSERTION)
        assert vr.passed
        assert vr.strategy is VerificationStrategy.OUTPUT_ASSERTION

    def test_output_assertion_fails_on_failed_result(self) -> None:
        vr = engine.verify(step(), fail_result(), VerificationStrategy.OUTPUT_ASSERTION)
        assert not vr.passed

    def test_readonly_strategy_passes_without_output(self) -> None:
        vr = engine.verify(step(), ok_result(), VerificationStrategy.NONE_READONLY)
        assert vr.passed

    def test_readonly_still_fails_if_tool_failed(self) -> None:
        vr = engine.verify(step(), fail_result(), VerificationStrategy.NONE_READONLY)
        assert not vr.passed

    def test_timed_out_result_fails_verification(self) -> None:
        timed_out = ToolResult(invocation_id="i1", ok=False, timed_out=True)
        vr = engine.verify(step(), timed_out, VerificationStrategy.OUTPUT_ASSERTION)
        assert not vr.passed
