import pytest

from omnimac_daemon.macos.app_control import AppInfo, MockAppControl
from omnimac_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation
from omnimac_daemon.tools.app_tools import AppFocus, AppLaunch, AppList, register_app_tools
from omnimac_daemon.tools.registry import ToolRegistry


async def test_app_list_maps_running() -> None:
    ac = MockAppControl(running=[AppInfo(name="Finder", bundle_id="f", active=True)])
    tool = AppList(ac)
    out = await tool.run(tool.input_model(), dry_run=False)
    assert out.running[0].name == "Finder" and out.running[0].active is True


async def test_app_launch_success_with_state_probe() -> None:
    ac = MockAppControl()
    tool = AppLaunch(ac)
    out = await tool.run(tool.input_model(app="Safari"), dry_run=False)
    assert out.launched is True and "Safari" in [a.name for a in ac.list_running()]
    assert ac.frontmost() is not None and ac.frontmost().name == "Safari"
    verification = tool.verify_independently(tool.input_model(app="Safari"))
    assert verification is not None and verification.passed is True


async def test_app_launch_probe_failure_raises() -> None:
    ac = MockAppControl(add_on_launch=False)  # launch returns True but app never appears
    tool = AppLaunch(ac)
    with pytest.raises(RuntimeError):
        await tool.run(tool.input_model(app="Safari"), dry_run=False)


async def test_app_launch_activation_failure_raises() -> None:
    class _CannotActivate(MockAppControl):
        def activate(self, name: str) -> bool:
            return False

    tool = AppLaunch(_CannotActivate())
    with pytest.raises(RuntimeError, match="activate"):
        await tool.run(tool.input_model(app="Safari"), dry_run=False)


async def test_app_launch_dry_run_noop() -> None:
    ac = MockAppControl()
    tool = AppLaunch(ac)
    out = await tool.run(tool.input_model(app="Safari"), dry_run=True)
    assert out.launched is False and ac.launched == []


async def test_app_focus_sets_frontmost() -> None:
    ac = MockAppControl(
        running=[
            AppInfo(name="Finder", bundle_id="f", active=True),
            AppInfo(name="Safari", bundle_id="s", active=False),
        ]
    )
    tool = AppFocus(ac)
    out = await tool.run(tool.input_model(app="Safari"), dry_run=False)
    assert out.focused is True and ac.frontmost().name == "Safari"
    verification = tool.verify_independently(tool.input_model(app="Safari"))
    assert verification is not None and verification.passed is True


async def test_app_focus_unknown_raises() -> None:
    ac = MockAppControl(running=[AppInfo(name="Finder", bundle_id="f", active=True)])
    tool = AppFocus(ac)
    with pytest.raises(RuntimeError):
        await tool.run(tool.input_model(app="Nope"), dry_run=False)


def test_launch_requests_app_scope() -> None:
    tool = AppLaunch(MockAppControl())
    assert tool.requested_scope(tool.input_model(app="Safari")).apps == ["Safari"]


async def test_registry_backstop_refuses_ungranted_app() -> None:
    reg = ToolRegistry()
    register_app_tools(reg, adapter=MockAppControl())
    inv = ToolInvocation(
        task_id="t",
        step_id="s",
        tool_name="app_launch",
        arguments={"app": "Terminal"},
        effective_risk=RiskLevel.R1,
    )
    # allowed apps = {Safari}; Terminal is not granted -> refused before launch.
    result = await reg.execute(inv, ResourceScope(apps=["Safari"]))
    assert not result.ok and "scope violation" in (result.error or "")


async def test_registry_backstop_allows_granted_app() -> None:
    ac = MockAppControl()
    reg = ToolRegistry()
    register_app_tools(reg, adapter=ac)
    inv = ToolInvocation(
        task_id="t",
        step_id="s",
        tool_name="app_launch",
        arguments={"app": "Safari"},
        effective_risk=RiskLevel.R1,
    )
    result = await reg.execute(inv, ResourceScope(apps=["Safari"]))
    assert result.ok and "Safari" in ac.launched
