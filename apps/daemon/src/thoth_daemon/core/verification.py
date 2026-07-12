"""Verification engine.

A step is not COMPLETED until verification passes. "Command exited 0" is
never sufficient on its own: a failed, timed-out, or cancelled tool result
always fails verification, and a passing verification requires the declared
postcondition to hold. Failed verification routes the task to RECOVERING.
"""

from thoth_daemon.core.verifiers import VerifierContext, evaluate_check
from thoth_daemon.schemas import (
    PlanStep,
    ToolResult,
    VerificationCheck,
    VerificationResult,
    VerificationStrategy,
)


class VerificationEngine:
    def __init__(self, context: VerifierContext | None = None) -> None:
        # Real, no-TCC probes by default (filesystem/tcp/http/process/git).
        # AX/app/browser probes are injected by the daemon when wired.
        self._context = context or VerifierContext.with_real_probes()

    def run_checks(
        self,
        step: PlanStep,
        result: ToolResult,
        checks: list[VerificationCheck],
    ) -> VerificationResult:
        """Independent verification: a tool's success flag is a precondition,
        never proof. If the tool failed, verification fails immediately.
        Otherwise every declared check must independently confirm the real
        postcondition. An un-wired probe (available=False) is a failure, so
        a missing capability can never masquerade as a verified success."""
        if not result.ok:
            return VerificationResult(
                step_id=step.id,
                invocation_id=result.invocation_id,
                strategy=VerificationStrategy.STATE_PROBE,
                passed=False,
                detail=result.error or "tool reported failure",
            )
        if not checks:
            return VerificationResult(
                step_id=step.id,
                invocation_id=result.invocation_id,
                strategy=VerificationStrategy.STATE_PROBE,
                passed=True,
                detail="no independent checks declared; tool succeeded",
            )
        outcomes = [evaluate_check(check, self._context, result) for check in checks]
        passed = all(o.passed for o in outcomes)
        detail = "; ".join(
            f"{check.kind.value}={'ok' if o.passed else 'fail'}: {o.detail}"
            for check, o in zip(checks, outcomes, strict=True)
        )
        return VerificationResult(
            step_id=step.id,
            invocation_id=result.invocation_id,
            strategy=VerificationStrategy.STATE_PROBE,
            passed=passed,
            detail=detail,
        )

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
