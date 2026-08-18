"""Approval engine.

Every R2+ tool invocation requires an explicit approval that is:
  - single-use (consumed on first authorization),
  - bound to one exact ToolInvocation.id,
  - unexpired (TTL from the moment of request),
  - granted immediately before execution.

Missing / denied / mismatched / expired / already-consumed -> execution is
blocked (ApprovalRequiredError) and the caller audits ``execution_blocked``.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from omnimac_daemon.schemas import ApprovalRequest, ApprovalStatus, RiskLevel


def _default_clock() -> datetime:
    return datetime.now(UTC)


class ApprovalRequiredError(Exception):
    """Raised when an execution is attempted without a valid, unconsumed,
    unexpired approval bound to that invocation."""


class UnknownApprovalError(Exception):
    """Raised when deciding a request id that does not exist or was already
    decided."""


class _Grant:
    __slots__ = ("arguments", "consumed", "expires_at", "invocation_id", "request_id")

    def __init__(
        self,
        request_id: str,
        invocation_id: str,
        arguments: dict[str, Any],
        expires_at: datetime,
    ) -> None:
        self.request_id = request_id
        self.invocation_id = invocation_id
        self.arguments = arguments
        self.expires_at = expires_at
        self.consumed = False


class ApprovalEngine:
    def __init__(
        self,
        ttl_seconds: int = 120,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock
        self._requests: dict[str, ApprovalRequest] = {}
        self._grants: dict[str, _Grant] = {}  # keyed by invocation_id

    def request(
        self,
        task_id: str,
        invocation_id: str,
        step_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk: RiskLevel,
        reason: str,
        target: str,
    ) -> ApprovalRequest:
        now = self._clock()
        req = ApprovalRequest(
            task_id=task_id,
            invocation_id=invocation_id,
            step_id=step_id,
            tool_name=tool_name,
            arguments=arguments,
            risk=risk,
            reason=reason,
            target=target,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._requests[req.id] = req
        return req

    def decide(
        self,
        request_id: str,
        approved: bool,
        modified_arguments: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        req = self._requests.get(request_id)
        if req is None or req.status is not ApprovalStatus.PENDING:
            raise UnknownApprovalError(f"no pending approval '{request_id}'")

        if not approved:
            req.status = ApprovalStatus.DENIED
            return req

        req.status = ApprovalStatus.APPROVED
        args = modified_arguments if modified_arguments is not None else req.arguments
        if modified_arguments is not None:
            req.arguments = modified_arguments
        self._grants[req.invocation_id] = _Grant(
            request_id=req.id,
            invocation_id=req.invocation_id,
            arguments=args,
            expires_at=req.expires_at,
        )
        return req

    def authorize_execution(self, invocation_id: str) -> _Grant:
        grant = self._grants.get(invocation_id)
        if grant is None:
            raise ApprovalRequiredError(f"no approval granted for invocation '{invocation_id}'")
        if grant.consumed:
            raise ApprovalRequiredError(f"approval for invocation '{invocation_id}' was already used")
        if self._clock() > grant.expires_at:
            raise ApprovalRequiredError(f"approval for invocation '{invocation_id}' has expired")
        grant.consumed = True
        return grant

    def pending(self) -> list[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status is ApprovalStatus.PENDING]

    def get(self, request_id: str) -> ApprovalRequest:
        req = self._requests.get(request_id)
        if req is None:
            raise UnknownApprovalError(f"no approval '{request_id}'")
        return req

    def expire_stale(self) -> None:
        """Mark timed-out pending requests EXPIRED. Advisory bookkeeping;
        authorize_execution enforces expiry regardless."""
        now = self._clock()
        for req in self._requests.values():
            if req.status is ApprovalStatus.PENDING and now > req.expires_at:
                req.status = ApprovalStatus.EXPIRED

    def invalidate_for_task(self, task_id: str) -> set[str]:
        """Revoke every unused approval associated with one task.

        Pending requests and approved-but-not-consumed grants are invalidated.
        Already consumed grants describe an effect that may have begun and are
        left as approved audit history; cancellation still reaches the runner.
        """
        invalidated: set[str] = set()
        for request in self._requests.values():
            if request.task_id != task_id:
                continue
            if request.status is ApprovalStatus.PENDING:
                request.status = ApprovalStatus.INVALIDATED
                invalidated.add(request.id)
                continue
            grant = self._grants.get(request.invocation_id)
            if request.status is ApprovalStatus.APPROVED and grant is not None and not grant.consumed:
                request.status = ApprovalStatus.INVALIDATED
                invalidated.add(request.id)
                self._grants.pop(request.invocation_id, None)
        return invalidated

    def invalidate_all(self) -> set[str]:
        """Revoke all pending and granted-but-unused approval authority."""
        invalidated: set[str] = set()
        task_ids = {request.task_id for request in self._requests.values()}
        for task_id in task_ids:
            invalidated.update(self.invalidate_for_task(task_id))
        return invalidated
