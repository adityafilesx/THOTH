"""Bounded recovery (Phase 4 slice 8 semantics).

Limits: ≤2 retries/step, ≤2 replans/task, recovery depth ≤3 episodes,
and the orchestrator additionally caps ≤25 tool executions/task. When a
budget is exhausted the controller ESCALATES to the user
(FAILED_REQUIRES_USER) instead of failing silently. Denials (policy or
approval) still fail immediately and never touch any budget.
"""

from omnimac_daemon.core.recovery import RecoveryController
from omnimac_daemon.schemas import ToolResult


def transient_fail() -> ToolResult:
    return ToolResult(invocation_id="i", ok=False, error="transient", timed_out=True)


def hard_fail() -> ToolResult:
    return ToolResult(invocation_id="i", ok=False, error="boom")


class TestRetryLimits:
    def test_retries_transient_failure_up_to_step_limit_then_replans(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=2, max_retries_per_task=5)
        d1 = ctrl.on_step_failure("t1", "s1", transient_fail(), verification_failed=False)
        d2 = ctrl.on_step_failure("t1", "s1", transient_fail(), verification_failed=False)
        d3 = ctrl.on_step_failure("t1", "s1", transient_fail(), verification_failed=False)
        assert d1.action == "retry" and d1.attempt == 1
        assert d2.action == "retry" and d2.attempt == 2
        assert d3.action == "replan"  # step budget exhausted -> try a new plan

    def test_task_budget_routes_to_replan(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=5, max_retries_per_task=2)
        assert ctrl.on_step_failure("t1", "s1", transient_fail(), False).action == "retry"
        assert ctrl.on_step_failure("t1", "s2", transient_fail(), False).action == "retry"
        # third retry anywhere in the task exceeds the task budget -> replan
        assert ctrl.on_step_failure("t1", "s3", transient_fail(), False).action == "replan"

    def test_verification_failure_is_retryable(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=2, max_retries_per_task=5)
        d = ctrl.on_step_failure("t1", "s1", ToolResult(invocation_id="i", ok=True), True)
        assert d.action == "retry"


class TestReplanAndEscalation:
    def test_replans_exhaust_then_escalate(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=0, max_replans_per_task=2)
        d1 = ctrl.on_step_failure("t1", "s1", transient_fail(), False)
        d2 = ctrl.on_step_failure("t1", "s2", transient_fail(), False)
        d3 = ctrl.on_step_failure("t1", "s3", transient_fail(), False)
        assert d1.action == "replan"
        assert d2.action == "replan"
        assert d3.action == "escalate"
        assert "user" in d3.reason.lower() or "exhaust" in d3.reason.lower()

    def test_replan_resets_per_task_retry_budget(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=5, max_retries_per_task=1)
        assert ctrl.on_step_failure("t1", "s1", transient_fail(), False).action == "retry"
        # task retry budget now exhausted -> replan
        assert ctrl.on_step_failure("t1", "s1b", transient_fail(), False).action == "replan"
        # after a replan the fresh plan gets a fresh task retry budget
        assert ctrl.on_step_failure("t1", "s2", transient_fail(), False).action == "retry"

    def test_recovery_depth_cap_escalates(self) -> None:
        # Depth = consecutive failing recovery episodes (a step's retry run =
        # one episode; each replan opens a new episode). max_depth=2 means the
        # third distinct failing episode escalates even with replans left.
        ctrl = RecoveryController(max_retries_per_step=0, max_replans_per_task=9, max_recovery_depth=2)
        assert ctrl.on_step_failure("t1", "s1", transient_fail(), False).action == "replan"
        assert ctrl.on_step_failure("t1", "s2", transient_fail(), False).action == "replan"
        assert ctrl.on_step_failure("t1", "s3", transient_fail(), False).action == "escalate"

    def test_step_success_resets_depth_chain(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=0, max_replans_per_task=9, max_recovery_depth=2)
        assert ctrl.on_step_failure("t1", "s1", transient_fail(), False).action == "replan"
        ctrl.on_step_success("t1")  # a verified success breaks the chain
        assert ctrl.on_step_failure("t1", "s2", transient_fail(), False).action == "replan"
        assert ctrl.on_step_failure("t1", "s3", transient_fail(), False).action == "replan"

    def test_default_limits_match_spec(self) -> None:
        ctrl = RecoveryController()
        assert ctrl.max_retries_per_step == 2
        assert ctrl.max_replans_per_task == 2
        assert ctrl.max_recovery_depth == 3


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

    def test_cancelled_result_is_not_retryable(self) -> None:
        ctrl = RecoveryController()
        cancelled = ToolResult(invocation_id="i", ok=False, cancelled=True, error="cancelled")
        assert ctrl.on_step_failure("t1", "s1", cancelled, False).action == "fail"


class TestAuditability:
    def test_every_decision_names_task_and_step(self) -> None:
        ctrl = RecoveryController(max_retries_per_step=1, max_retries_per_task=3)
        d = ctrl.on_step_failure("task-9", "step-3", transient_fail(), False)
        assert d.task_id == "task-9" and d.step_id == "step-3"
        assert d.reason
