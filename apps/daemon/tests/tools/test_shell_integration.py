from pathlib import Path

from thoth_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation
from thoth_daemon.tools.registry import ToolRegistry
from thoth_daemon.tools.shell_tool import register_shell_tool


def _inv(args: dict) -> ToolInvocation:
    return ToolInvocation(
        task_id="t", step_id="s", tool_name="shell_run", arguments=args, effective_risk=RiskLevel.R2
    )


async def test_backstop_refuses_out_of_scope_arg(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_shell_tool(reg)
    allowed = ResourceScope(paths=[str(tmp_path)])
    result = await reg.execute(_inv({"command": "cat /etc/hosts", "cwd": str(tmp_path)}), allowed)
    assert not result.ok and "scope violation" in (result.error or "")


async def test_backstop_allows_in_scope_command(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hi")
    reg = ToolRegistry()
    register_shell_tool(reg)
    allowed = ResourceScope(paths=[str(tmp_path)])
    result = await reg.execute(_inv({"command": "cat a.txt", "cwd": str(tmp_path)}), allowed)
    assert result.ok
    assert result.output is not None and result.output["stdout"] == "[REDACTED]"  # masked


async def test_backstop_refuses_denylisted_arg() -> None:
    reg = ToolRegistry()
    register_shell_tool(reg)
    allowed = ResourceScope(paths=[str(Path.home())])
    result = await reg.execute(
        _inv({"command": "cat .ssh/id_rsa", "cwd": str(Path.home())}), allowed
    )
    assert not result.ok and "scope violation" in (result.error or "")
