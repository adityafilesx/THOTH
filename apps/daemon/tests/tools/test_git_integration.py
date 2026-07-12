from pathlib import Path

from thoth_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation
from thoth_daemon.tools.git_io import run_git
from thoth_daemon.tools.git_tools import register_git_tools
from thoth_daemon.tools.registry import ToolRegistry


def _inv(name: str, args: dict) -> ToolInvocation:
    return ToolInvocation(
        task_id="t", step_id="s", tool_name=name, arguments=args, effective_risk=RiskLevel.R0
    )


async def test_status_in_scope_ok(tmp_path: Path) -> None:
    await run_git(tmp_path, ["init"])
    reg = ToolRegistry()
    register_git_tools(reg)
    result = await reg.execute(
        _inv("git_status", {"cwd": str(tmp_path)}), ResourceScope(paths=[str(tmp_path)])
    )
    assert result.ok


async def test_status_out_of_scope_refused(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_git_tools(reg)
    result = await reg.execute(
        _inv("git_status", {"cwd": str(tmp_path / "repo")}),
        ResourceScope(paths=[str(tmp_path / "other")]),
    )
    assert not result.ok and "scope violation" in (result.error or "")


async def test_add_out_of_scope_path_refused(tmp_path: Path) -> None:
    await run_git(tmp_path, ["init"])
    reg = ToolRegistry()
    register_git_tools(reg)
    result = await reg.execute(
        _inv("git_add", {"cwd": str(tmp_path), "paths": ["../../../etc/hosts"]}),
        ResourceScope(paths=[str(tmp_path)]),
    )
    assert not result.ok and "scope violation" in (result.error or "")
