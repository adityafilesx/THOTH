"""Restricted shell tool (Phase 3 slice 4). The ONLY tool that accepts a
command string — but it is not a shell: allowlisted executable, argv via
create_subprocess_exec (shell=False), scoped cwd + argument paths, R2 approval
per command, output cap, redaction, SIGTERM->SIGKILL cancel."""

from __future__ import annotations

import asyncio
import contextlib
import shlex
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from thoth_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from thoth_daemon.security.paths import expand_and_resolve
from thoth_daemon.security.shell_policy import (
    CONTROLLED_PATH,
    ShellPolicyError,
    parse_command,
    validate_executable,
)
from thoth_daemon.tools.base import ToolDefinition
from thoth_daemon.tools.registry import ToolRegistry

_MAX_OUTPUT = 32 * 1024
_KILL_GRACE_S = 2.0


class ShellRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str
    cwd: str


class ShellRunOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str
    executed: bool
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool


def _cap(data: bytes) -> tuple[str, bool]:
    truncated = len(data) > _MAX_OUTPUT
    return data[:_MAX_OUTPUT].decode("utf-8", errors="replace"), truncated


class ShellRun(ToolDefinition[ShellRunIn, ShellRunOut]):
    name = "shell_run"
    description = "Run an allowlisted command (no shell) in an approved directory."
    input_model = ShellRunIn
    output_model = ShellRunOut
    default_risk = RiskLevel.R2
    supports_dry_run = True
    timeout_s = 30.0
    verification = VerificationStrategy.OUTPUT_ASSERTION
    redaction_fields: ClassVar[list[str]] = ["stdout", "stderr"]

    def requested_scope(self, args: ShellRunIn) -> ResourceScope:
        try:
            p = parse_command(args.command, args.cwd)
        except ShellPolicyError:
            return ResourceScope(paths=[args.cwd])
        return ResourceScope(paths=[args.cwd, *p.path_tokens])

    async def run(self, args: ShellRunIn, dry_run: bool) -> ShellRunOut:
        p = parse_command(args.command, args.cwd)  # raises ShellPolicyError -> failed result
        validate_executable(p.argv)
        cwd = expand_and_resolve(args.cwd)
        if not cwd.is_dir():
            raise NotADirectoryError(f"cwd is not a directory: {cwd}")
        if dry_run:
            return ShellRunOut(
                command=args.command,
                executed=False,
                exit_code=0,
                stdout="[dry-run] " + shlex.join(p.argv),
                stderr="",
                truncated=False,
            )
        proc = await asyncio.create_subprocess_exec(
            *p.argv,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PATH": CONTROLLED_PATH, "HOME": str(expand_and_resolve("~"))},
        )
        try:
            out, err = await proc.communicate()
        except asyncio.CancelledError:
            await self._terminate(proc)
            raise
        stdout, t1 = _cap(out)
        stderr, t2 = _cap(err)
        code = proc.returncode if proc.returncode is not None else -1
        if code != 0:
            raise RuntimeError(f"command exited {code}: {stderr[:500]}")
        return ShellRunOut(
            command=args.command,
            executed=True,
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            truncated=t1 or t2,
        )

    @staticmethod
    async def _terminate(proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=_KILL_GRACE_S)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()


def register_shell_tool(registry: ToolRegistry) -> None:
    registry.register(ShellRun())
