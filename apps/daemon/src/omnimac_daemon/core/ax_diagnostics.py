"""Bounded, non-persistent Accessibility diagnostics for the desktop."""

from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from omnimac_daemon.core.ax_resolver import AXResolutionResult
from omnimac_daemon.core.focus import FocusPolicy
from omnimac_daemon.schemas.ax import AXElementQuery, AXVerificationResult


class AXSemanticTargetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identifier: str | None = Field(default=None, max_length=4096)
    role: str | None = Field(default=None, max_length=4096)
    semantic_alias: str | None = Field(default=None, max_length=4096)


class AXDiagnosticsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    current_task_id: str | None = None
    current_step_id: str | None = None
    current_tool: str | None = None
    bundle_id: str | None = None
    semantic_target: AXSemanticTargetSummary | None = None
    resolution_method: str | None = None
    resolution_confidence: float | None = Field(default=None, ge=0, le=1)
    candidate_count: int | None = Field(default=None, ge=0, le=500)
    focus_policy: FocusPolicy | None = None
    verification_evidence: str | None = Field(default=None, max_length=4096)
    permission_error: str | None = Field(default=None, max_length=4096)
    clarification_required: bool = False
    updated_at: datetime | None = None


class AXDiagnosticsStore:
    """Keep only the latest redacted semantic operation in process memory."""

    max_retained_snapshots: ClassVar[int] = 1

    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = AXDiagnosticsSnapshot()

    def snapshot(self) -> AXDiagnosticsSnapshot:
        with self._lock:
            return self._snapshot.model_copy(deep=True)

    def bind(
        self,
        *,
        task_id: str,
        step_id: str,
        tool_name: str,
        bundle_id: str,
        query: AXElementQuery | None,
        focus_policy: FocusPolicy,
        now: datetime,
    ) -> None:
        target = (
            AXSemanticTargetSummary(
                identifier=query.identifier,
                role=query.role,
                semantic_alias=query.semantic_alias,
            )
            if query is not None
            else None
        )
        with self._lock:
            self._snapshot = AXDiagnosticsSnapshot(
                current_task_id=task_id,
                current_step_id=step_id,
                current_tool=tool_name,
                bundle_id=bundle_id,
                semantic_target=target,
                focus_policy=focus_policy,
                updated_at=now,
            )

    def record_resolution(self, result: AXResolutionResult, *, now: datetime) -> None:
        with self._lock:
            self._snapshot = self._snapshot.model_copy(
                update={
                    "resolution_method": result.method.value if result.method else None,
                    "resolution_confidence": result.confidence,
                    "candidate_count": result.candidate_count,
                    "clarification_required": result.ambiguous,
                    "verification_evidence": result.rejection_reason,
                    "updated_at": now,
                }
            )

    def record_verification(self, result: AXVerificationResult, *, now: datetime) -> None:
        with self._lock:
            self._snapshot = self._snapshot.model_copy(
                update={
                    "verification_evidence": (f"{result.expectation.value}={'verified' if result.passed else 'failed'}: {result.detail}"),
                    "updated_at": now,
                }
            )

    def record_permission_error(self, detail: str, *, now: datetime) -> None:
        with self._lock:
            self._snapshot = self._snapshot.model_copy(update={"permission_error": detail, "updated_at": now})
