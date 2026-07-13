"""Persona integration over authoritative live task state."""

from datetime import UTC, datetime, timedelta

from thoth_daemon.core.focus import FocusPolicy, FocusRestorationResult
from thoth_daemon.core.foreground import ForegroundContext
from thoth_daemon.core.persona import ResponseIntent
from thoth_daemon.core.runtime_status import LocalRuntimeStatus
from thoth_daemon.core.task_presentation import (
    ApprovalStage,
    TaskPresentationComposer,
)
from thoth_daemon.schemas import (
    ApprovalRequest,
    ExecutionPlan,
    PlanStep,
    RiskLevel,
    StepStatus,
    Task,
    TaskSource,
    TaskState,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _step(
    *,
    status: StepStatus = StepStatus.PENDING,
    verified: bool | None = None,
    risk: RiskLevel = RiskLevel.R0,
) -> PlanStep:
    return PlanStep(
        index=0,
        title="Run checks",
        tool_name="shell_run",
        arguments={"command": "pytest", "cwd": "/workspace"},
        declared_risk=risk,
        focus_policy=FocusPolicy.DO_NOT_STEAL_FOCUS,
        status=status,
        verification_passed=verified,
        verification_detail="checks passed" if verified else None,
    )


def _task(state: TaskState, steps: list[PlanStep] | None = None, error: str | None = None) -> Task:
    task = Task(goal="Run the checks", source=TaskSource.TEXT, state=state, error=error)
    if steps is not None:
        task.plan = ExecutionPlan(task_id=task.id, summary="Run checks", steps=steps)
    return task


COMPOSER = TaskPresentationComposer()


class TestLifecycleIntents:
    def test_task_created_acknowledgement(self) -> None:
        view = COMPOSER.compose(_task(TaskState.RECEIVED))
        assert view.response.intent is ResponseIntent.ACKNOWLEDGEMENT
        assert view.response.used_model is False

    def test_plan_ready_response(self) -> None:
        view = COMPOSER.compose(_task(TaskState.RISK_REVIEW, [_step()]))
        assert view.response.intent is ResponseIntent.PLAN_READY
        assert view.stages.proposed is True

    def test_approval_required_response_is_deterministic(self) -> None:
        task = _task(TaskState.WAITING_FOR_APPROVAL, [_step(risk=RiskLevel.R2)])
        approval = ApprovalRequest(
            task_id=task.id,
            invocation_id="i1",
            step_id=task.plan.steps[0].id,
            tool_name="shell_run",
            risk=RiskLevel.R2,
            reason="explicit approval required",
            target="cwd=/workspace",
        )
        view = COMPOSER.compose(task, pending_approvals=[approval])
        assert view.response.intent is ResponseIntent.APPROVAL_REQUIRED
        assert "Nothing has been sent" in view.display_response
        assert view.stages.approval is ApprovalStage.PENDING
        assert view.response.used_model is False

    def test_execution_progress(self) -> None:
        view = COMPOSER.compose(_task(TaskState.EXECUTING, [_step(status=StepStatus.RUNNING)]))
        assert view.response.intent is ResponseIntent.EXECUTION_PROGRESS
        assert view.stages.executed is True

    def test_verified_completion(self) -> None:
        view = COMPOSER.compose(
            _task(TaskState.COMPLETED, [_step(status=StepStatus.SUCCEEDED, verified=True)])
        )
        assert view.response.intent is ResponseIntent.VERIFIED_COMPLETION
        assert view.stages.verified is True

    def test_partial_completion_does_not_hide_failed_substep(self) -> None:
        ok = _step(status=StepStatus.SUCCEEDED, verified=True)
        failed = _step(status=StepStatus.FAILED, verified=False).model_copy(
            update={"id": "failed", "index": 1, "title": "Start frontend"}
        )
        view = COMPOSER.compose(
            _task(TaskState.FAILED, [ok, failed], error="port 5173 is occupied")
        )
        assert view.response.intent is ResponseIntent.PARTIAL_COMPLETION
        assert "Run checks" in view.display_response
        assert "Start frontend" in view.display_response
        assert "5173" in view.display_response

    def test_policy_refusal_uses_actual_reason_without_model(self) -> None:
        view = COMPOSER.compose(
            _task(TaskState.FAILED, [_step()], error="step blocked by scope: outside workspace")
        )
        assert view.response.intent is ResponseIntent.POLICY_REFUSAL
        assert "outside workspace" in view.display_response
        assert view.response.used_model is False

    def test_failure_and_interruption(self) -> None:
        failed = COMPOSER.compose(_task(TaskState.FAILED, error="file not found"))
        stopped = COMPOSER.compose(_task(TaskState.CANCELLED))
        assert failed.response.intent is ResponseIntent.FAILED
        assert stopped.response.intent is ResponseIntent.INTERRUPTED

    def test_resumable_task(self) -> None:
        view = COMPOSER.compose(
            _task(TaskState.FAILED_REQUIRES_USER, [_step()], error="retry budget exhausted")
        )
        assert view.response.intent is ResponseIntent.RESUMABLE_TASK


class TestOperationalFacts:
    def test_model_runtime_failure_uses_deterministic_degraded_response(self) -> None:
        task = _task(
            TaskState.FAILED,
            error="planning failed: local model inference endpoint unavailable",
        )
        view = COMPOSER.compose(task, runtime_status=LocalRuntimeStatus.UNAVAILABLE)
        assert view.response.intent is ResponseIntent.DEGRADED_MODE
        assert view.response.used_model is False
        assert "local model" in view.display_response.lower()

    def test_focus_restoration_failure_makes_completion_partial(self) -> None:
        task = _task(TaskState.COMPLETED, [_step(status=StepStatus.SUCCEEDED, verified=True)])
        focus = FocusRestorationResult(
            restored=False,
            verified=False,
            final_bundle_id="com.apple.TextEdit",
            detail="restoration unverified",
        )
        view = COMPOSER.compose(task, focus_result=focus)
        assert view.response.intent is ResponseIntent.PARTIAL_COMPLETION
        assert "restoration unverified" in view.display_response
        assert view.stages.verified is False

    def test_foreground_runtime_workspace_and_dialogue_are_preserved(self) -> None:
        foreground = ForegroundContext(
            captured_at=NOW,
            reason="status",
            active_bundle_id="com.microsoft.VSCode",
            active_app_name="Visual Studio Code",
            workspace_id="thoth",
        )
        expires = NOW + timedelta(minutes=5)
        view = COMPOSER.compose(
            _task(TaskState.EXECUTING, [_step(status=StepStatus.RUNNING)]),
            runtime_status=LocalRuntimeStatus.DEGRADED,
            foreground=foreground,
            dialogue_expires_at=expires,
        )
        assert view.runtime_status is LocalRuntimeStatus.DEGRADED
        assert view.foreground == foreground
        assert view.matched_workspace_id == "thoth"
        assert view.dialogue_expires_at == expires
        assert view.planned_focus_policy is FocusPolicy.DO_NOT_STEAL_FOCUS

    def test_spoken_preview_is_not_longer_than_display(self) -> None:
        view = COMPOSER.compose(
            _task(TaskState.COMPLETED, [_step(status=StepStatus.SUCCEEDED, verified=True)])
        )
        assert len(view.spoken_response_preview) <= len(view.display_response)
