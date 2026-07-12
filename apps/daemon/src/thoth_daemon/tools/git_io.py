"""Subprocess helper for the git tools: run git with a controlled environment,
capped output, and a timeout. Pure I/O; callers decide what a non-zero exit
code means."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path

from thoth_daemon.security.paths import expand_and_resolve
from thoth_daemon.security.shell_policy import CONTROLLED_PATH

_MAX_OUTPUT = 64 * 1024
_KILL_GRACE_S = 2.0


@dataclass
class GitResult:
    returncode: int
    stdout: str
    stderr: str
    truncated: bool


def _cap(data: bytes) -> tuple[str, bool]:
    truncated = len(data) > _MAX_OUTPUT
    return data[:_MAX_OUTPUT].decode("utf-8", errors="replace"), truncated


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


async def run_git(cwd: Path, args: list[str], timeout: float = 30.0) -> GitResult:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            "PATH": CONTROLLED_PATH,
            "HOME": str(expand_and_resolve("~")),
            "GIT_TERMINAL_PROMPT": "0",
        },
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        await _terminate(proc)
        raise
    stdout, t1 = _cap(out)
    stderr, t2 = _cap(err)
    code = proc.returncode if proc.returncode is not None else -1
    return GitResult(returncode=code, stdout=stdout, stderr=stderr, truncated=t1 or t2)
