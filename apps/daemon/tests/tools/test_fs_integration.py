from pathlib import Path

from omnimac_daemon.core.scope import ScopeEnforcer, ScopeViolation
from omnimac_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation
from omnimac_daemon.tools.fs_tools import FsReadFile, register_fs_tools
from omnimac_daemon.tools.registry import ToolRegistry


def _inv(name: str, args: dict) -> ToolInvocation:
    return ToolInvocation(task_id="t", step_id="s", tool_name=name, arguments=args, effective_risk=RiskLevel.R0)


async def test_registry_backstop_allows_in_scope_read(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hi")
    reg = ToolRegistry()
    register_fs_tools(reg)
    allowed = ResourceScope(paths=[str(tmp_path)])
    result = await reg.execute(_inv("fs_read_file", {"path": str(tmp_path / "a.txt")}), allowed)
    assert result.ok
    assert result.output is not None
    assert result.output["content"] == "[REDACTED]"  # content masked in the echoed output


async def test_registry_backstop_refuses_out_of_scope(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_fs_tools(reg)
    allowed = ResourceScope(paths=[str(tmp_path / "approved")])
    result = await reg.execute(_inv("fs_read_file", {"path": str(tmp_path / "elsewhere.txt")}), allowed)
    assert not result.ok and "scope violation" in (result.error or "")


def test_enforcer_refuses_denylisted_even_in_scope() -> None:
    enforcer = ScopeEnforcer()
    tool = FsReadFile()
    allowed = ResourceScope(paths=[str(Path.home())])
    args = tool.input_model(path=str(Path.home() / ".ssh" / "id_rsa"))
    try:
        enforcer.check(tool.requested_scope(args), allowed)
        raise AssertionError("expected ScopeViolation")
    except ScopeViolation as exc:
        assert "denied" in exc.reason


async def test_symlink_escape_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s")
    (root / "link.txt").symlink_to(outside / "secret.txt")
    reg = ToolRegistry()
    register_fs_tools(reg)
    allowed = ResourceScope(paths=[str(root)])
    result = await reg.execute(_inv("fs_read_file", {"path": str(root / "link.txt")}), allowed)
    assert not result.ok and "scope violation" in (result.error or "")
