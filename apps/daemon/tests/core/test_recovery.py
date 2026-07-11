from thoth_daemon.core.recovery import RecoveryController
from thoth_daemon.schemas import ToolResult


def transient_fail() -> ToolResult:
    return ToolResult(invocation_id="i", ok=False, error="transient", timed_out=True)


def hard_fail() -> ToolResult:
    return ToolResult(invocation_id="i", ok=False, error="boom")


class TestRetryLimits:
    def test_retries_transient_failure_up_to_step_limit(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=2, max_retries_per_task=5)
        d1 = ctrl.on_step_failure("t1", "s1", transient_fail(), verification_failed=False)
        d2 = ctrl.on_step_failure("t1", "s1", transient_fail(), verification_failed=False)
        d3 = ctrl.on_step_failure("t1", "s1", transient_fail(), verification_failed=False)
        assert d1.action == "retry" and d1.attempt == 1
        assert d2.action == "retry" and d2.attempt == 2
        assert d3.action == "fail"  # step budget exhausted

    def test_task_budget_caps_total_retries_across_steps(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=5, max_retries_per_task=2)
        assert ctrl.on_step_failure("t1", "s1", transient_fail(), False).action == "retry"
        assert ctrl.on_step_failure("t1", "s2", transient_fail(), False).action == "retry"
        # third retry anywhere in the task exceeds the task budget
        assert ctrl.on_step_failure("t1", "s3", transient_fail(), False).action == "fail"

    def test_verification_failure_is_retryable(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=2, max_retries_per_task=5)
        d = ctrl.on_step_failure("t1", "s1", ToolResult(invocation_id="i", ok=True), True)
        assert d.action == "retry"


class TestNonRetryable:
    def test_policy_denial_never_retried(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=2, max_retries_per_task=5)
        d = ctrl.on_denied("t1", "s1", reason="R3 blocked by policy")
        assert d.action == "fail"
        assert "polic" in d.reason.lower() or "denied" in d.reason.lower()

    def test_approval_denial_never_retried(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=2, max_retries_per_task=5)
        d = ctrl.on_denied("t1", "s1", reason="approval denied by user")
        assert d.action == "fail"

    def test_denials_do_not_consume_retry_budget(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=2, max_retries_per_task=5)
        ctrl.on_denied("t1", "s1", reason="approval denied")
        # a later transient failure still gets its full step budget
        d = ctrl.on_step_failure("t1", "s2", transient_fail(), False)
        assert d.action == "retry" and d.attempt == 1


class TestAuditability:
    def test_every_decision_names_task_and_step(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=1, max_retries_per_task=3)
        d = ctrl.on_step_failure("task-9", "step-3", transient_fail(), False)
        assert d.task_id == "task-9" and d.step_id == "step-3"
        assert d.reason
