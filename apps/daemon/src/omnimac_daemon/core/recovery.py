"""Recovery controller — bounded retries, replans, and escalation.

Retries only transient failures (tool timeouts, transient exceptions) and
failed verifications. NEVER retries policy denials or approval denials —
those fail the step immediately and do not consume any budget.

Phase 4 slice 8 bounds (spec):
  - ≤ ``max_retries_per_step`` retries of the same step (default 2)
  - ≤ ``max_replans_per_task`` full replans (default 2); a replan resets
    the per-task retry budget for the fresh plan
  - recovery depth ≤ ``max_recovery_depth`` consecutive failing episodes
    (default 3): a step's retry run is one episode, each replan opens a
    new one; a verified step success breaks the chain
  - the orchestrator additionally caps total tool executions per task

When any bound is exhausted the decision is ESCALATE — the task must end
in FAILED_REQUIRES_USER so a human decides, never a silent failure and
never an unbounded loop. Every decision is a typed RecoveryDecision for
the audit trail.
"""

from omnimac_daemon.schemas import RecoveryDecision, ToolResult


class RecoveryController:
    def __init__(
        self,
        max_retries_per_step: int = 2,
        max_retries_per_task: int = 5,
        max_replans_per_task: int = 2,
        max_recovery_depth: int = 3,
    ) -> None:
        self.max_retries_per_step = max_retries_per_step
        self.max_retries_per_task = max_retries_per_task
        self.max_replans_per_task = max_replans_per_task
        self.max_recovery_depth = max_recovery_depth
        self._step_attempts: dict[tuple[str, str], int] = {}
        self._task_attempts: dict[str, int] = {}
        self._replans: dict[str, int] = {}
        # Consecutive failing recovery episodes since the last verified
        # success; an episode is opened per distinct failing step.
        self._episodes: dict[str, set[str]] = {}

    def on_step_failure(
        self,
        task_id: str,
        step_id: str,
        result: ToolResult,
        verification_failed: bool,
    ) -> RecoveryDecision:
        retryable = verification_failed or result.timed_out or (not result.ok and not result.cancelled)
        if not retryable:
            return RecoveryDecision(
                task_id=task_id,
                step_id=step_id,
                action="fail",
                attempt=self._step_attempts.get((task_id, step_id), 0),
                reason="non-retryable failure",
            )

        episodes = self._episodes.setdefault(task_id, set())
        episodes.add(step_id)
        if len(episodes) > self.max_recovery_depth:
            return self._escalate(
                task_id,
                step_id,
                f"recovery depth exhausted ({self.max_recovery_depth} consecutive failing episodes); user intervention required",
            )

        step_done = self._step_attempts.get((task_id, step_id), 0)
        task_done = self._task_attempts.get(task_id, 0)
        if step_done < self.max_retries_per_step and task_done < self.max_retries_per_task:
            self._step_attempts[(task_id, step_id)] = step_done + 1
            self._task_attempts[task_id] = task_done + 1
            return RecoveryDecision(
                task_id=task_id,
                step_id=step_id,
                action="retry",
                attempt=step_done + 1,
                reason="transient failure; retrying",
            )

        replans_done = self._replans.get(task_id, 0)
        if replans_done < self.max_replans_per_task:
            self._replans[task_id] = replans_done + 1
            # A fresh plan gets a fresh retry budget — still bounded by the
            # replan count, the episode depth, and the orchestrator's
            # execution cap.
            self._task_attempts[task_id] = 0
            return RecoveryDecision(
                task_id=task_id,
                step_id=step_id,
                action="replan",
                attempt=replans_done + 1,
                reason=f"retry budget exhausted; replanning ({replans_done + 1}/{self.max_replans_per_task})",
            )

        return self._escalate(
            task_id,
            step_id,
            f"retry and replan budgets exhausted ({self.max_retries_per_step}/step, {self.max_replans_per_task} replans); user intervention required",
        )

    def on_step_success(self, task_id: str) -> None:
        """A verified step success breaks the consecutive-failure chain."""
        self._episodes.pop(task_id, None)

    def on_denied(self, task_id: str, step_id: str, reason: str) -> RecoveryDecision:
        """Policy or approval denial: fail immediately, never retry, do not
        touch any budget."""
        return RecoveryDecision(
            task_id=task_id,
            step_id=step_id,
            action="fail",
            attempt=0,
            reason=f"denied, not retryable: {reason}",
        )

    def _escalate(self, task_id: str, step_id: str, reason: str) -> RecoveryDecision:
        return RecoveryDecision(
            task_id=task_id,
            step_id=step_id,
            action="escalate",
            attempt=self._step_attempts.get((task_id, step_id), 0),
            reason=reason,
        )
