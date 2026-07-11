import asyncio

import pytest
from pydantic import ValidationError

from thoth_daemon.schemas import RiskLevel, ToolInvocation
from thoth_daemon.tools.base import DuplicateToolError, ToolDefinition, UnknownToolError
from thoth_daemon.tools.mock_tools import build_registry
from thoth_daemon.tools.registry import ToolRegistry


@pytest.fixture()
def registry() -> ToolRegistry:
    return build_registry()


def invocation(
    tool_name: str, arguments: dict[str, object], dry_run: bool = False
) -> ToolInvocation:
    return ToolInvocation(
        task_id="t1",
        step_id="s1",
        tool_name=tool_name,
        arguments=arguments,
        effective_risk=RiskLevel.R0,
        dry_run=dry_run,
    )


class TestRegistration:
    def test_unknown_tool_lookup_raises(self, registry: ToolRegistry) -> None:
        with pytest.raises(UnknownToolError):
            registry.get("does_not_exist")

    def test_duplicate_registration_raises(self, registry: ToolRegistry) -> None:
        existing = registry.get("mock_read_file")
        with pytest.raises(DuplicateToolError):
            registry.register(existing)

    def test_default_risk_lookup(self, registry: ToolRegistry) -> None:
        assert registry.default_risk("mock_send_email") is RiskLevel.R2
        assert registry.default_risk("mock_delete_dir") is RiskLevel.R3
        assert registry.default_risk("nope") is None

    def test_every_tool_satisfies_contract(self, registry: ToolRegistry) -> None:
        for tool in registry.all():
            assert isinstance(tool, ToolDefinition)
            assert tool.name.startswith("mock_")
            assert tool.timeout_s > 0
            assert tool.description


class TestArgumentValidation:
    async def test_unknown_tool_execution_raises(self, registry: ToolRegistry) -> None:
        with pytest.raises(UnknownToolError):
            await registry.execute(invocation("nope", {}))

    async def test_extra_argument_rejected(self, registry: ToolRegistry) -> None:
        with pytest.raises(ValidationError):
            await registry.execute(invocation("mock_read_file", {"path": "/x", "extra": 1}))

    async def test_missing_argument_rejected(self, registry: ToolRegistry) -> None:
        with pytest.raises(ValidationError):
            await registry.execute(invocation("mock_read_file", {}))

    async def test_wrong_type_rejected(self, registry: ToolRegistry) -> None:
        with pytest.raises(ValidationError):
            await registry.execute(invocation("mock_read_file", {"path": 123}))


class TestExecution:
    async def test_happy_path_read(self, registry: ToolRegistry) -> None:
        result = await registry.execute(invocation("mock_read_file", {"path": "/tmp/notes.md"}))
        assert result.ok
        assert result.output is not None

    async def test_timeout_enforced(self, registry: ToolRegistry) -> None:
        result = await registry.execute(invocation("mock_slow", {"sleep_s": 5}))
        assert not result.ok
        assert result.timed_out

    async def test_cancellation_reports_cancelled(self, registry: ToolRegistry) -> None:
        inv = invocation("mock_slow", {"sleep_s": 5})
        task = asyncio.ensure_future(registry.execute(inv))
        await asyncio.sleep(0.05)
        task.cancel()
        result = await task
        assert result.cancelled and not result.ok

    async def test_dry_run_has_no_side_effect(self, registry: ToolRegistry) -> None:
        tool = registry.get("mock_edit_file")
        args = {"path": "/tmp/x.txt", "content": "hello"}
        await registry.execute(invocation("mock_edit_file", args, dry_run=True))
        assert tool.side_effect_count == 0  # type: ignore[attr-defined]
        await registry.execute(invocation("mock_edit_file", args, dry_run=False))
        assert tool.side_effect_count == 1  # type: ignore[attr-defined]

    async def test_flaky_tool_fails_then_succeeds(self, registry: ToolRegistry) -> None:
        first = await registry.execute(invocation("mock_flaky", {"fail_times": 2}))
        second = await registry.execute(invocation("mock_flaky", {"fail_times": 2}))
        third = await registry.execute(invocation("mock_flaky", {"fail_times": 2}))
        assert not first.ok and not second.ok and third.ok


class TestRedaction:
    async def test_declared_redaction_fields_applied_in_result(
        self, registry: ToolRegistry
    ) -> None:
        result = await registry.execute(
            invocation(
                "mock_send_email",
                {"recipient": "a@b.c", "subject": "s", "body": "secret plan"},
            )
        )
        assert result.output is not None
        # Tool declares recipient+body as redaction fields; echoed output masks them.
        assert result.output.get("recipient") == "[REDACTED]"
        assert result.output.get("body") == "[REDACTED]"
        assert result.output.get("subject") == "s"
