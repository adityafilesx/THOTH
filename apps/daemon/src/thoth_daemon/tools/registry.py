"""Tool registry and executor.

The registry is the single lookup for tools: unknown names and duplicate
registrations are rejected. ``execute`` validates arguments, enforces the
per-tool timeout, honors cooperative cancellation, applies declared
redaction to the echoed output, and always returns a typed ToolResult
(never raises for tool-level failures — only for programmer errors like
unknown tool / invalid arguments).
"""

import asyncio
import time
from typing import Any

from thoth_daemon.core.focus import FocusPolicy
from thoth_daemon.core.scope import ScopeEnforcer, ScopeViolation
from thoth_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation, ToolResult
from thoth_daemon.security.redaction import redact
from thoth_daemon.tools.base import (
    DuplicateToolError,
    InvalidToolDefinitionError,
    ToolDefinition,
    UnknownToolError,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition[Any, Any]] = {}
        self._enforcer = ScopeEnforcer()

    def register(self, tool: ToolDefinition[Any, Any]) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(f"tool '{tool.name}' already registered")
        if not isinstance(getattr(tool, "focus_policy", None), FocusPolicy):
            raise InvalidToolDefinitionError(
                f"tool '{tool.name}' has no valid authoritative focus_policy"
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition[Any, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(f"unknown tool '{name}'")
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def default_risk(self, name: str) -> RiskLevel | None:
        tool = self._tools.get(name)
        return tool.default_risk if tool else None

    def all(self) -> list[ToolDefinition[Any, Any]]:
        return list(self._tools.values())

    async def execute(
        self, invocation: ToolInvocation, allowed_scope: ResourceScope | None = None
    ) -> ToolResult:
        tool = self.get(invocation.tool_name)  # raises UnknownToolError
        args = tool.parse_arguments(invocation)  # raises ValidationError
        tool.validate_authority(args)

        # Backstop scope check — no tool runs against an out-of-scope target,
        # even via a direct registry call. The orchestrator gate is primary.
        try:
            self._enforcer.check(tool.requested_scope(args), allowed_scope or ResourceScope())
        except ScopeViolation as exc:
            return ToolResult(
                invocation_id=invocation.id, ok=False, error=f"scope violation: {exc}"
            )

        started = time.perf_counter()
        try:
            output = await asyncio.wait_for(
                tool.run(args, dry_run=invocation.dry_run),
                timeout=tool.timeout_s,
            )
        except TimeoutError:
            return ToolResult(
                invocation_id=invocation.id,
                ok=False,
                error=f"tool '{tool.name}' timed out after {tool.timeout_s}s",
                duration_ms=(time.perf_counter() - started) * 1000,
                timed_out=True,
            )
        except asyncio.CancelledError:
            return ToolResult(
                invocation_id=invocation.id,
                ok=False,
                error="cancelled",
                duration_ms=(time.perf_counter() - started) * 1000,
                cancelled=True,
            )
        except Exception as exc:  # tool errors are surfaced as a typed failure
            return ToolResult(
                invocation_id=invocation.id,
                ok=False,
                error=str(exc),
                duration_ms=(time.perf_counter() - started) * 1000,
            )

        payload: dict[str, Any] = output.model_dump()
        redacted = redact(payload, extra_fields=tool.redaction_fields)
        return ToolResult(
            invocation_id=invocation.id,
            ok=True,
            output=redacted,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
