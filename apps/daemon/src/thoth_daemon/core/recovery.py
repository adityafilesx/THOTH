"""Recovery controller — bounded retries.

Retries only transient failures (tool timeouts, transient exceptions) and
failed verifications. NEVER retries policy denials or approval denials —
those fail the step immediately and do not consume the retry budget.
Enforces per-step and per-task retry ceilings; exhaustion fails the task.
Every decision is a typed RecoveryDecision for the audit trail.
"""

from thoth_daemon.schemas import RecoveryDecision, ToolResult


class RecoveryController:
    def __init__(self, max_retries_per_step: int = 2, max_retries_per_task: int = 5) -> None:
        self._max_step = max_retries_per_step
        self._max_task = max_retries_per_task
        self._step_attempts: dict[tuple[str, str], int] = {}
        self._task_attempts: dict[str, int] = {}

    def on_step_failure(
        self,
        task_id: str,
        step_id: str,
        result: ToolResult,
        verification_failed: bool,
    ) -> RecoveryDecision:
        retryable = (
            verification_failed or result.timed_out or (not result.ok and not result.cancelled)
        )
        if not retryable:
            return RecoveryDecision(
                task_id=task_id,
                step_id=step_id,
                action="fail",
                attempt=self._step_attempts.get((task_id, step_id), 0),
                reason="non-retryable failure",
            )

        step_done = self._step_attempts.get((task_id, step_id), 0)
        task_done = self._task_attempts.get(task_id, 0)
        if step_done >= self._max_step:
            return RecoveryDecision(
                task_id=task_id,
                step_id=step_id,
                action="fail",
                attempt=step_done,
                reason=f"per-step retry budget exhausted ({self._max_step})",
            )
        if task_done >= self._max_task:
            return RecoveryDecision(
                task_id=task_id,
                step_id=step_id,
                action="fail",
                attempt=task_done,
                reason=f"per-task retry budget exhausted ({self._max_task})",
            )

        self._step_attempts[(task_id, step_id)] = step_done + 1
        self._task_attempts[task_id] = task_done + 1
        return RecoveryDecision(
            task_id=task_id,
            step_id=step_id,
            action="retry",
            attempt=step_done + 1,
            reason="transient failure; retrying",
        )

    def on_denied(self, task_id: str, step_id: str, reason: str) -> RecoveryDecision:
        """Policy or approval denial: fail immediately, never retry, do not
        touch the retry budget."""
        return RecoveryDecision(
            task_id=task_id,
            step_id=step_id,
            action="fail",
            attempt=0,
            reason=f"denied, not retryable: {reason}",
        )
