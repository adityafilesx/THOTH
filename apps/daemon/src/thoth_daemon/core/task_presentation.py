"""Deterministic persona integration over authoritative task state.

This adapter derives display facts from the task, approvals, verification,
runtime, foreground, dialogue, and focus results. It cannot execute tools and
never asks a model to phrase approval, refusal, failure, or routine progress.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from thoth_daemon.core.focus import FocusPolicy, FocusRestorationResult
from thoth_daemon.core.foreground import ForegroundContext
from thoth_daemon.core.persona import (
    AccessibilityOutcome,
    PersonaResponse,
    PersonaResponseComposer,
    ResponseFact,
    ResponseIntent,
    ResponseMode,
    ResponsePolicyViolation,
)
from thoth_daemon.core.runtime_status import LocalRuntimeStatus
from thoth_daemon.schemas import ApprovalRequest, PlanStep, RiskLevel, StepStatus, Task, TaskState

_UNSAFE_PLAN_FAILURE_MARKERS = (
    "bad_arguments",
    "malformed",
    "missing_verifier",
    "risk_downgrade",
    "unknown_tool",
    "unsupported_app",
    "validation error",
    "pydantic.dev",
)


def _user_safe_failure_reason(error: str) -> str:
    lowered = error.lower()
    if lowered.startswith("planning failed:") and any(
        marker in lowered for marker in _UNSAFE_PLAN_FAILURE_MARKERS
    ):
        return "I could not build a valid plan. No action was taken."
    return error


class ApprovalStage(StrEnum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class TaskStageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposed: bool
    approval: ApprovalStage
    executed: bool
    verified: bool


class TaskPresentation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    authoritative: bool = True
    response: PersonaResponse
    display_response: str
    spoken_response_preview: str
    foreground: ForegroundContext | None = None
    matched_workspace_id: str | None = None
    planned_focus_policy: FocusPolicy | None = None
    focus_result: FocusRestorationResult | None = None
    runtime_status: LocalRuntimeStatus
    dialogue_expires_at: datetime | None = None
    stages: TaskStageSummary


class TaskPresentationComposer:
    def __init__(self, persona: PersonaResponseComposer | None = None) -> None:
        self._persona = persona or PersonaResponseComposer()

    def compose(
        self,
        task: Task,
        *,
        pending_approvals: list[ApprovalRequest] | None = None,
        runtime_status: LocalRuntimeStatus = LocalRuntimeStatus.UNAVAILABLE,
        foreground: ForegroundContext | None = None,
        focus_result: FocusRestorationResult | None = None,
        dialogue_expires_at: datetime | None = None,
        mode: ResponseMode = ResponseMode.STANDARD,
    ) -> TaskPresentation:
        approvals = [a for a in (pending_approvals or []) if a.task_id == task.id]
        fact = self._fact(task, approvals, focus_result, runtime_status)
        try:
            response = self._persona.compose(fact, mode)
        except ResponsePolicyViolation:
            # Untrusted planner titles/reasons may contain persona-policy
            # phrases. Preserve structured task truth but phrase a safe,
            # deterministic fallback instead of echoing the directive.
            response = self._persona.compose(self._safe_fact(task, fact), mode)

        stages = self._stages(task, approvals, focus_result)
        planned_focus = None
        if task.plan:
            active = next(
                (step for step in task.plan.steps if step.status is not StepStatus.SUCCEEDED),
                task.plan.steps[-1] if task.plan.steps else None,
            )
            planned_focus = active.focus_policy if active else None

        return TaskPresentation(
            task_id=task.id,
            response=response,
            display_response=response.display.text,
            spoken_response_preview=response.spoken.text,
            foreground=foreground,
            matched_workspace_id=foreground.workspace_id if foreground else None,
            planned_focus_policy=planned_focus,
            focus_result=focus_result,
            runtime_status=runtime_status,
            dialogue_expires_at=dialogue_expires_at,
            stages=stages,
        )

    @staticmethod
    def _fact(
        task: Task,
        approvals: list[ApprovalRequest],
        focus_result: FocusRestorationResult | None,
        runtime_status: LocalRuntimeStatus,
    ) -> ResponseFact:
        state = task.state
        steps = task.plan.steps if task.plan else []
        succeeded = [step.title for step in steps if step.status is StepStatus.SUCCEEDED]
        failed_steps = [step for step in steps if step.status is StepStatus.FAILED]

        accessibility_fact = TaskPresentationComposer._accessibility_fact(
            task,
            steps,
            focus_result,
        )
        if accessibility_fact is not None:
            return accessibility_fact

        if state in {TaskState.RECEIVED, TaskState.UNDERSTANDING}:
            return ResponseFact(intent=ResponseIntent.ACKNOWLEDGEMENT)
        if state is TaskState.PLANNING:
            return ResponseFact(
                intent=ResponseIntent.EXECUTION_PROGRESS,
                step_progress="Preparing a plan.",
            )
        if state is TaskState.RISK_REVIEW:
            return ResponseFact(intent=ResponseIntent.PLAN_READY)
        if state is TaskState.WAITING_FOR_APPROVAL:
            approval = approvals[0] if approvals else None
            target = (
                f"run {approval.tool_name} for {approval.target}"
                if approval
                else "perform the pending action"
            )
            return ResponseFact(
                intent=ResponseIntent.APPROVAL_REQUIRED,
                risk=approval.risk.value if approval else "R2",
                approval_target=target,
            )
        if state in {TaskState.EXECUTING, TaskState.VERIFYING, TaskState.RECOVERING}:
            running = next(
                (
                    step
                    for step in steps
                    if step.status in {StepStatus.RUNNING, StepStatus.VERIFYING}
                ),
                None,
            )
            progress = f"Working on {running.title}." if running else "Working."
            return ResponseFact(
                intent=ResponseIntent.EXECUTION_PROGRESS,
                step_progress=progress,
            )
        if state is TaskState.COMPLETED:
            if focus_result is not None and not focus_result.verified:
                return ResponseFact(
                    intent=ResponseIntent.PARTIAL_COMPLETION,
                    succeeded_items=succeeded,
                    failed_items=[f"Focus: {focus_result.detail}"],
                    verified=False,
                )
            return ResponseFact(
                intent=ResponseIntent.VERIFIED_COMPLETION,
                succeeded_items=succeeded or [task.result_summary or "The task is complete"],
                verified=bool(steps) and all(step.verification_passed is True for step in steps),
            )
        if state is TaskState.CANCELLED:
            return ResponseFact(intent=ResponseIntent.INTERRUPTED)
        if state is TaskState.FAILED_REQUIRES_USER:
            resumable = next(
                (step.title for step in steps if step.status is not StepStatus.SUCCEEDED),
                "the failed step",
            )
            return ResponseFact(
                intent=ResponseIntent.RESUMABLE_TASK,
                resumable_step=resumable,
                failure_reason=task.error,
            )
        if state is TaskState.FAILED and succeeded:
            failed = [
                f"{step.title} failed: {task.error or step.verification_detail or 'unverified'}"
                for step in failed_steps
            ] or [f"Remaining work failed: {task.error or 'unverified'}"]
            return ResponseFact(
                intent=ResponseIntent.PARTIAL_COMPLETION,
                succeeded_items=succeeded,
                failed_items=failed,
                failure_reason=task.error,
                verified=False,
            )
        if state is TaskState.FAILED:
            error = task.error or "an error occurred"
            runtime_failed = runtime_status.persona_intent() is ResponseIntent.DEGRADED_MODE
            model_dependent_failure = any(
                token in error.lower()
                for token in (
                    "inference",
                    "local model",
                    "local plan",
                    "model endpoint",
                    "ollama",
                )
            )
            if runtime_failed and model_dependent_failure:
                return ResponseFact(
                    intent=ResponseIntent.DEGRADED_MODE,
                    failure_reason=error,
                    verified=False,
                )
            if "blocked by policy" in error.lower() or "blocked by scope" in error.lower():
                return ResponseFact(
                    intent=ResponseIntent.POLICY_REFUSAL,
                    failure_reason=error,
                    verified=False,
                )
            return ResponseFact(
                intent=ResponseIntent.FAILED,
                failure_reason=_user_safe_failure_reason(error),
                verified=False,
            )
        return ResponseFact(intent=ResponseIntent.ACKNOWLEDGEMENT)

    @staticmethod
    def _accessibility_fact(
        task: Task,
        steps: list[PlanStep],
        focus_result: FocusRestorationResult | None,
    ) -> ResponseFact | None:
        """Map authoritative AX execution state to fixed persona outcomes.

        Planner-authored titles and expected-result prose are deliberately not
        used. The error text is classified into a closed enum and is never
        echoed. Application names come only from this local bundle allowlist.
        """
        ax_steps = [step for step in steps if step.tool_name.startswith("ax.")]
        if not ax_steps or task.state not in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.FAILED_REQUIRES_USER,
            TaskState.CANCELLED,
        }:
            return None

        ax_step = ax_steps[-1]
        bundle_id = ax_step.arguments.get("bundle_id")
        application_names = {
            "com.apple.finder": "Finder",
            "com.apple.TextEdit": "TextEdit",
            "com.microsoft.VSCode": "Visual Studio Code",
            "com.apple.Terminal": "Terminal",
            "me.adityalabs.thoth.axtest": "THOTH Accessibility Test App",
            "com.google.Chrome": "Chromium",
            "org.chromium.Chromium": "Chromium",
        }
        application_name = (
            application_names.get(bundle_id, "the approved application")
            if isinstance(bundle_id, str)
            else "the approved application"
        )

        def fact(intent: ResponseIntent, outcome: AccessibilityOutcome) -> ResponseFact:
            return ResponseFact(
                intent=intent,
                accessibility_outcome=outcome,
                application_name=application_name,
                verified=outcome is AccessibilityOutcome.ACTION_VERIFIED,
            )

        if task.state is TaskState.CANCELLED:
            return fact(ResponseIntent.INTERRUPTED, AccessibilityOutcome.ACTION_CANCELLED)

        if task.state is TaskState.COMPLETED:
            if focus_result is not None and not focus_result.verified:
                return fact(
                    ResponseIntent.PARTIAL_COMPLETION,
                    AccessibilityOutcome.FOCUS_RESTORATION_FAILED,
                )
            if not all(step.verification_passed is True for step in ax_steps):
                return fact(
                    ResponseIntent.PARTIAL_COMPLETION,
                    AccessibilityOutcome.PARTIAL_COMPLETION,
                )
            return fact(
                ResponseIntent.VERIFIED_COMPLETION,
                AccessibilityOutcome.ACTION_VERIFIED,
            )

        evidence = " ".join(
            part for part in (task.error, ax_step.verification_detail) if isinstance(part, str)
        ).lower()
        if "revoked" in evidence:
            return fact(ResponseIntent.FAILED, AccessibilityOutcome.PERMISSION_REVOKED)
        if any(
            token in evidence
            for token in (
                "axpermissionerror",
                "permission",
                "not_determined",
                "not determined",
                "tcc",
            )
        ):
            return fact(ResponseIntent.FAILED, AccessibilityOutcome.PERMISSION_MISSING)
        if any(token in evidence for token in ("multiple", "ambiguous", "clarification")):
            return fact(
                ResponseIntent.NEEDS_CLARIFICATION,
                AccessibilityOutcome.MULTIPLE_ELEMENTS,
            )
        if "disabled" in evidence:
            return fact(ResponseIntent.FAILED, AccessibilityOutcome.ELEMENT_DISABLED)
        if "stale" in evidence:
            return fact(ResponseIntent.FAILED, AccessibilityOutcome.STALE_REFERENCE)
        if any(token in evidence for token in ("application closed", "not running", "terminated")):
            return fact(ResponseIntent.FAILED, AccessibilityOutcome.APPLICATION_CLOSED)
        if any(
            token in evidence
            for token in ("capability", "unauthorized", "unsupported", "forbidden")
        ):
            return fact(
                ResponseIntent.POLICY_REFUSAL,
                AccessibilityOutcome.UNSUPPORTED_CAPABILITY,
            )
        if any(token in evidence for token in ("not found", "did not resolve", "no match")):
            return fact(ResponseIntent.FAILED, AccessibilityOutcome.ELEMENT_NOT_FOUND)
        if any(step.status is StepStatus.SUCCEEDED for step in ax_steps):
            return fact(
                ResponseIntent.PARTIAL_COMPLETION,
                AccessibilityOutcome.PARTIAL_COMPLETION,
            )
        return None

    @staticmethod
    def _safe_fact(task: Task, original: ResponseFact) -> ResponseFact:
        steps = task.plan.steps if task.plan else []
        succeeded = [
            f"Step {step.index + 1} verified"
            for step in steps
            if step.status is StepStatus.SUCCEEDED
        ]
        failed = [
            f"Step {step.index + 1} failed" for step in steps if step.status is StepStatus.FAILED
        ]
        return original.model_copy(
            update={
                "summary": "",
                "succeeded_items": succeeded,
                "failed_items": failed,
                "failure_reason": "The authoritative task state records a failure.",
                "step_progress": "Working.",
                "approval_target": "perform the pending action",
                "resumable_step": "the recorded step",
            }
        )

    @staticmethod
    def _stages(
        task: Task,
        approvals: list[ApprovalRequest],
        focus_result: FocusRestorationResult | None,
    ) -> TaskStageSummary:
        steps = task.plan.steps if task.plan else []
        approval_required = any(step.declared_risk.rank >= RiskLevel.R2.rank for step in steps)
        if task.error and "approval denied" in task.error.lower():
            approval = ApprovalStage.DENIED
        elif approvals or task.state is TaskState.WAITING_FOR_APPROVAL:
            approval = ApprovalStage.PENDING
        elif approval_required and any(step.status is not StepStatus.PENDING for step in steps):
            approval = ApprovalStage.APPROVED
        elif approval_required:
            approval = ApprovalStage.REQUIRED
        else:
            approval = ApprovalStage.NOT_REQUIRED

        executed = any(step.status is not StepStatus.PENDING for step in steps)
        verified = (
            task.state is TaskState.COMPLETED
            and bool(steps)
            and all(step.verification_passed is True for step in steps)
            and (focus_result is None or focus_result.verified)
        )
        return TaskStageSummary(
            proposed=task.plan is not None,
            approval=approval,
            executed=executed,
            verified=verified,
        )


def task_event_payload(
    task: Task,
    pending_approvals: list[ApprovalRequest] | None = None,
    focus_result: FocusRestorationResult | None = None,
) -> dict[str, object]:
    """WS sibling payload: raw task truth plus deterministic presentation."""
    presentation = TaskPresentationComposer().compose(
        task,
        pending_approvals=pending_approvals,
        focus_result=focus_result,
    )
    return {
        "task": task.model_dump(mode="json"),
        "presentation": presentation.model_dump(mode="json"),
    }
