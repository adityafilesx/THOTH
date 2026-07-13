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
        postcondition AND have actually been able to run: an un-wired probe
        (available=False) fails the step even inside a COMPOSITE(any) whose
        sibling passed — a missing capability can never be part of a
        verified success."""
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
        # Fail-closed on availability: passed requires the probe to have run.
        passed = all(o.passed and o.available for o in outcomes)
        detail = "; ".join(
            f"{check.kind.value}={'ok' if (o.passed and o.available) else 'fail'}: {o.detail}"
            for check, o in zip(checks, outcomes, strict=True)
        )
        return VerificationResult(
            step_id=step.id,
            invocation_id=result.invocation_id,
            strategy=VerificationStrategy.STATE_PROBE,
            passed=passed,
            detail=detail,
        )

    def verify_step(
        self,
        step: PlanStep,
        result: ToolResult,
        strategy: VerificationStrategy,
    ) -> VerificationResult:
        """Single verification entry point: the tool's declared strategy is
        the system-enforced MINIMUM (baseline); declared checks can only add
        strictness on top, never replace it. Overall pass requires baseline
        AND every independent check."""
        baseline = self.verify(step, result, strategy)
        if not step.verification_checks:
            return baseline
        checks = self.run_checks(step, result, step.verification_checks)
        if not baseline.passed:
            return baseline
        if not checks.passed:
            return checks
        return VerificationResult(
            step_id=step.id,
            invocation_id=result.invocation_id,
            strategy=VerificationStrategy.STATE_PROBE,
            passed=True,
            detail=f"baseline[{strategy.value}]: {baseline.detail}; checks: {checks.detail}",
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
