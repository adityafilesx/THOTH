"""Typed data contracts for every cross-boundary payload.

Rules:
- ``extra="forbid"`` everywhere: unknown fields are rejected, not ignored.
- These models are the API. Persistence rows live in storage/models.py.
- The model-generated plan is validated against these schemas (and the
  tool registry) BEFORE risk review.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from thoth_daemon.schemas.enums import (
    TRUSTED_PROVENANCE,
    ApprovalStatus,
    Provenance,
    RiskLevel,
    StepStatus,
    TaskSource,
    TaskState,
    VerificationStrategy,
)


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaggedContent(StrictModel):
    """A piece of context with explicit provenance. Untrusted content can
    never change objectives, approve actions, or expand permissions —
    enforced by core/injection_guard.py and by the policy engine consuming
    only trusted, typed fields."""

    content: str
    provenance: Provenance
    source: str | None = None

    @property
    def is_trusted(self) -> bool:
        return self.provenance in TRUSTED_PROVENANCE


class PlanStep(StrictModel):
    id: str = Field(default_factory=_new_id)
    correlation_id: str = Field(default_factory=_new_id)
    index: int = Field(ge=0)
    title: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    declared_risk: RiskLevel
    status: StepStatus = StepStatus.PENDING
    verification_passed: bool | None = None
    verification_detail: str | None = None


class ExecutionPlan(StrictModel):
    id: str = Field(default_factory=_new_id)
    correlation_id: str = Field(default_factory=_new_id)
    task_id: str
    summary: str
    steps: list[PlanStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _contiguous_indexes(self) -> "ExecutionPlan":
        indexes = [step.index for step in self.steps]
        if indexes != list(range(len(indexes))):
            raise ValueError("plan step indexes must be contiguous starting at 0")
        return self


class Task(StrictModel):
    id: str = Field(default_factory=_new_id)
    correlation_id: str = Field(default_factory=_new_id)
    goal: str
    source: TaskSource
    state: TaskState = TaskState.RECEIVED
    plan: ExecutionPlan | None = None
    result_summary: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ResourceScope(StrictModel):
    """What a tool is permitted to touch. Empty lists mean 'nothing of
    that kind' — scopes only ever widen through user-granted permissions."""

    paths: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    apps: list[str] = Field(default_factory=list)


class ToolInvocation(StrictModel):
    id: str = Field(default_factory=_new_id)
    correlation_id: str = Field(default_factory=_new_id)
    task_id: str
    step_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    effective_risk: RiskLevel
    dry_run: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class ToolResult(StrictModel):
    invocation_id: str
    correlation_id: str = Field(default_factory=_new_id)
    ok: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0
    timed_out: bool = False
    cancelled: bool = False


class VerificationResult(StrictModel):
    step_id: str
    correlation_id: str = Field(default_factory=_new_id)
    invocation_id: str | None = None
    strategy: VerificationStrategy
    passed: bool
    detail: str
    checked_at: datetime = Field(default_factory=_utcnow)


class ApprovalRequest(StrictModel):
    id: str = Field(default_factory=_new_id)
    correlation_id: str = Field(default_factory=_new_id)
    task_id: str
    invocation_id: str
    step_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel
    reason: str
    target: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime = Field(default_factory=lambda: _utcnow() + timedelta(seconds=120))


class ApprovalDecision(StrictModel):
    request_id: str
    approved: bool
    scope: Literal["once"] = "once"
    modified_arguments: dict[str, Any] | None = None
    decided_at: datetime = Field(default_factory=_utcnow)


class AuditEvent(StrictModel):
    event_id: str = Field(default_factory=_new_id)
    correlation_id: str = Field(default_factory=_new_id)
    task_id: str
    seq: int = Field(ge=0)
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class PolicyDecision(StrictModel):
    allowed: bool
    requires_approval: bool
    effective_risk: RiskLevel
    reasons: list[str] = Field(default_factory=list)


class RecoveryDecision(StrictModel):
    task_id: str
    step_id: str
    action: Literal["retry", "fail"]
    attempt: int = Field(ge=0)
    reason: str


class SkillDefinition(StrictModel):
    id: str = Field(default_factory=_new_id)
    name: str
    description: str
    workflow: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    enabled: bool = True


class WorkspaceProfile(StrictModel):
    id: str = Field(default_factory=_new_id)
    name: str
    root_path: str
    trusted: bool = False
    approved_domains: list[str] = Field(default_factory=list)
    approved_apps: list[str] = Field(default_factory=list)


PermissionKind = Literal["path", "domain", "app"]


class PermissionGrant(StrictModel):
    """A single user-granted widening of scope, bound to a workspace. Grants
    are created only through the trusted permissions API; untrusted content
    can never mint one (threats T1/T3)."""

    id: str = Field(default_factory=_new_id)
    workspace_id: str
    kind: PermissionKind
    value: str
    granted_at: datetime = Field(default_factory=_utcnow)
    revoked: bool = False
