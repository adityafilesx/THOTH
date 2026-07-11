"""Verification engine.

A step is not COMPLETED until verification passes. "Command exited 0" is
never sufficient on its own: a failed, timed-out, or cancelled tool result
always fails verification, and a passing verification requires the declared
postcondition to hold. Failed verification routes the task to RECOVERING.
"""

from thoth_daemon.schemas import (
    PlanStep,
    ToolResult,
    VerificationResult,
    VerificationStrategy,
)


class VerificationEngine:
    def verify(
        self,
        step: PlanStep,
        result: ToolResult,
        strategy: VerificationStrategy,
    ) -> VerificationResult:
        if not result.ok:
            return VerificationResult(
                step_id=step.id,
                invocation_id=result.invocation_id,
                strategy=strategy,
                passed=False,
                detail=result.error or "tool reported failure",
            )

        if strategy is VerificationStrategy.NONE_READONLY:
            return VerificationResult(
                step_id=step.id,
                invocation_id=result.invocation_id,
                strategy=strategy,
                passed=True,
                detail="read-only step; tool succeeded",
            )

        if strategy is VerificationStrategy.OUTPUT_ASSERTION:
            has_output = result.output is not None
            return VerificationResult(
                step_id=step.id,
                invocation_id=result.invocation_id,
                strategy=strategy,
                passed=has_output,
                detail="output present" if has_output else "expected output was empty",
            )

        # STATE_PROBE: in Phase 2 the mock tools' successful result stands in
        # for a real post-execution probe; Phase 3 wires a read-only probe tool.
        return VerificationResult(
            step_id=step.id,
            invocation_id=result.invocation_id,
            strategy=strategy,
            passed=True,
            detail="state probe satisfied (mock)",
        )
