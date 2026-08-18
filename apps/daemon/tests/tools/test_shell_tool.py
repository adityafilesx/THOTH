import asyncio
from pathlib import Path

import pytest

from omnimac_daemon.tools.shell_tool import ShellRun


def _tool() -> ShellRun:
    return ShellRun()


async def test_echo_runs_and_captures_stdout(tmp_path: Path) -> None:
    tool = _tool()
    out = await tool.run(tool.input_model(command="echo hello", cwd=str(tmp_path)), dry_run=False)
    assert out.executed and out.exit_code == 0 and out.stdout.strip() == "hello"


async def test_dry_run_executes_nothing(tmp_path: Path) -> None:
    tool = _tool()
    out = await tool.run(tool.input_model(command="echo hello", cwd=str(tmp_path)), dry_run=True)
    assert out.executed is False and out.stdout.startswith("[dry-run]")


async def test_nonzero_exit_is_failure(tmp_path: Path) -> None:
    tool = _tool()
    with pytest.raises(RuntimeError):
        await tool.run(tool.input_model(command="ls no_such_dir_here", cwd=str(tmp_path)), dry_run=False)


async def test_offlist_executable_refused(tmp_path: Path) -> None:
    tool = _tool()
    with pytest.raises(Exception):  # noqa: B017 - policy error; never spawns
        await tool.run(tool.input_model(command="sudo ls", cwd=str(tmp_path)), dry_run=False)


async def test_metacharacter_command_refused(tmp_path: Path) -> None:
    tool = _tool()
    with pytest.raises(Exception):  # noqa: B017 - policy error; never spawns
        await tool.run(tool.input_model(command="ls; echo hi", cwd=str(tmp_path)), dry_run=False)


def test_requested_scope_includes_cwd_and_path_args(tmp_path: Path) -> None:
    from omnimac_daemon.security.paths import expand_and_resolve

    tool = _tool()
    scope = tool.requested_scope(tool.input_model(command="cat /etc/hosts", cwd=str(tmp_path)))
    assert str(tmp_path) in scope.paths and str(expand_and_resolve("/etc/hosts")) in scope.paths


def test_requested_scope_metachar_falls_back_to_cwd(tmp_path: Path) -> None:
    tool = _tool()
    scope = tool.requested_scope(tool.input_model(command="ls; rm -rf ~", cwd=str(tmp_path)))
    assert scope.paths == [str(tmp_path)]  # best-effort; run() refuses it


def test_tool_contract_flags() -> None:
    tool = _tool()
    assert tool.default_risk.value == "R2"
    assert tool.supports_dry_run and tool.redaction_fields == ["stdout", "stderr"]


async def test_terminate_kills_running_process() -> None:
    proc = await asyncio.create_subprocess_exec("sleep", "30", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    assert proc.returncode is None
    await ShellRun._terminate(proc)
    assert proc.returncode is not None


async def test_run_cancellation_terminates(tmp_path: Path) -> None:
    tool = _tool()
    task = asyncio.ensure_future(tool.run(tool.input_model(command="find /", cwd=str(tmp_path)), dry_run=False))
    await asyncio.sleep(0.15)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
