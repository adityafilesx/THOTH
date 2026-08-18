"""AX tools (Phase 4 slice 3) — contract tests against MockAXAdapter.

Values read from AX elements are UNTRUSTED (external app state); the tools
return them as plain data. Element interaction (set/perform) is R1, scoped
by requested_scope(apps=[app]), dry-run safe, and self-checked (a set that
does not stick reports verified=False).
"""

import pytest

from omnimac_daemon.macos.ax import AXElementInfo, AXPermissionError, MockAXAdapter
from omnimac_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation
from omnimac_daemon.tools.ax_tools import (
    AXFindElement,
    AXInspectApplication,
    AXPerformAction,
    AXReadValue,
    AXSetValue,
    AXWaitForElement,
    register_ax_tools,
)
from omnimac_daemon.tools.registry import ToolRegistry


def _mock() -> MockAXAdapter:
    return MockAXAdapter(
        {
            "TestApp": [
                AXElementInfo(role="AXTextField", label="omnimac-input", value="", enabled=True),
                AXElementInfo(role="AXButton", label="omnimac-submit", value=None, enabled=True),
            ]
        }
    )


class _RaisingAdapter(MockAXAdapter):
    """Simulates a missing Accessibility permission (no TCC)."""

    def list_elements(self, app_name: str) -> list[AXElementInfo]:
        raise AXPermissionError("Accessibility permission not granted")


class TestRiskAndScope:
    def test_default_risks(self) -> None:
        ax = _mock()
        assert AXInspectApplication(ax).default_risk is RiskLevel.R0
        assert AXFindElement(ax).default_risk is RiskLevel.R0
        assert AXReadValue(ax).default_risk is RiskLevel.R0
        assert AXWaitForElement(ax).default_risk is RiskLevel.R0
        assert AXSetValue(ax).default_risk is RiskLevel.R1
        assert AXPerformAction(ax).default_risk is RiskLevel.R1

    def test_requested_scope_names_the_app(self) -> None:
        ax = _mock()
        tool = AXSetValue(ax)
        args = tool.input_model.model_validate({"app": "TestApp", "role": "AXTextField", "label": "omnimac-input", "value": "x"})
        assert tool.requested_scope(args) == ResourceScope(apps=["TestApp"])


class TestReadPaths:
    async def test_inspect_lists_elements(self) -> None:
        tool = AXInspectApplication(_mock())
        out = await tool.run(tool.input_model.model_validate({"app": "TestApp"}), False)
        assert len(out.elements) == 2
        assert out.elements[0].label == "omnimac-input"

    async def test_find_element(self) -> None:
        tool = AXFindElement(_mock())
        out = await tool.run(
            tool.input_model.model_validate({"app": "TestApp", "role": "AXButton", "label": "omnimac-submit"}),
            False,
        )
        assert out.found and out.element is not None

    async def test_read_value(self) -> None:
        tool = AXReadValue(_mock())
        out = await tool.run(
            tool.input_model.model_validate({"app": "TestApp", "role": "AXTextField", "label": "omnimac-input"}),
            False,
        )
        assert out.value == ""


class TestMutationPaths:
    async def test_set_value_self_checks(self) -> None:
        ax = _mock()
        tool = AXSetValue(ax)
        out = await tool.run(
            tool.input_model.model_validate({"app": "TestApp", "role": "AXTextField", "label": "omnimac-input", "value": "hi"}),
            False,
        )
        assert out.verified  # re-read after set matched
        assert ax.read_value("TestApp", "AXTextField", "omnimac-input") == "hi"

    async def test_set_value_dry_run_mutates_nothing(self) -> None:
        ax = _mock()
        tool = AXSetValue(ax)
        out = await tool.run(
            tool.input_model.model_validate({"app": "TestApp", "role": "AXTextField", "label": "omnimac-input", "value": "hi"}),
            True,
        )
        assert not out.verified
        assert ax.read_value("TestApp", "AXTextField", "omnimac-input") == ""

    async def test_perform_action_dry_run_is_inert(self) -> None:
        ax = _mock()
        tool = AXPerformAction(ax)
        await tool.run(
            tool.input_model.model_validate({"app": "TestApp", "role": "AXButton", "label": "omnimac-submit", "action": "AXPress"}),
            True,
        )
        assert ax.actions_performed == []

    async def test_missing_permission_is_a_clean_failure(self) -> None:
        tool = AXInspectApplication(_RaisingAdapter({}))
        with pytest.raises(AXPermissionError):
            await tool.run(tool.input_model.model_validate({"app": "TestApp"}), False)


class TestRegistration:
    def test_register_all_six(self) -> None:
        registry = ToolRegistry()
        register_ax_tools(registry, _mock())
        for name in (
            "ax_inspect_application",
            "ax_find_element",
            "ax_read_value",
            "ax_wait_for_element",
            "ax_set_value",
            "ax_perform_action",
        ):
            assert registry.has(name)

    async def test_execution_through_registry_respects_scope(self) -> None:
        """Registry backstop: an app outside the allowed scope is refused."""
        registry = ToolRegistry()
        register_ax_tools(registry, _mock())
        inv = ToolInvocation(
            task_id="t",
            step_id="s",
            tool_name="ax_set_value",
            arguments={
                "app": "TestApp",
                "role": "AXTextField",
                "label": "omnimac-input",
                "value": "x",
            },
            effective_risk=RiskLevel.R1,
        )
        result = await registry.execute(inv, ResourceScope(apps=[]))  # nothing approved
        assert not result.ok
        assert "scope" in (result.error or "").lower()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
