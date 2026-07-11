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

from thoth_daemon.schemas import RiskLevel, ToolInvocation, ToolResult
from thoth_daemon.security.redaction import redact
from thoth_daemon.tools.base import (
    DuplicateToolError,
    ToolDefinition,
    UnknownToolError,
)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition[Any, Any]] = {}

    def register(self, tool: ToolDefinition[Any, Any]) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(f"tool '{tool.name}' already registered")
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

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        tool = self.get(invocation.tool_name)  # raises UnknownToolError
        args = tool.parse_arguments(invocation)  # raises ValidationError

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
