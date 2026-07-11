# Restricted Shell Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** `shell_run` — the only command-string tool — executing an allowlisted binary via argv (no shell), in a scoped cwd, R2 approval-per-command, with argument-path containment, output cap, redaction, and SIGTERM→SIGKILL cancel.

**Architecture:** Pure `shell_policy.py` (allowlist, metachar rejection, argv + path-token parse). `ShellRun` tool whose `requested_scope` returns `[cwd, *path_tokens]` so the slice-1 enforcer contains every path the command touches; `run()` adds allowlist + `create_subprocess_exec(shell=False)` + cap + cancel. Added alongside the mocks/fs tools.

**Tech Stack:** Python 3.12, asyncio subprocess, Pydantic v2, pytest.

## Global Constraints

- mypy strict + ruff clean. `extra="forbid"` inputs.
- No shell: `create_subprocess_exec` only; commands with `;&|`$()<>*?{}` newline are rejected.
- Only `EXECUTABLE_ALLOWLIST` binaries, bare command name (no `/`), controlled PATH.
- Default risk **R2** — every command needs an explicit single-use approval.
- Existing 322 daemon + 46 desktop tests stay green (additive).
- Branch `phase-3/restricted-shell`. Commit trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No push.

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `apps/daemon/src/thoth_daemon/security/shell_policy.py` | Create | allowlist, metachars, `parse_command`, `validate_executable`, `ShellPolicyError`. |
| `apps/daemon/src/thoth_daemon/tools/shell_tool.py` | Create | `ShellRun` + `register_shell_tool`. |
| `apps/daemon/src/thoth_daemon/app.py` | Modify | `register_shell_tool(registry)`. |
| `docs/DECISIONS.md`, `docs/THREAT_MODEL.md`, `docs/STATUS.md`, `docs/MILESTONES.md` | Modify | ADR-014 + status. |

Tests: `tests/security/test_shell_policy.py`, `tests/tools/test_shell_tool.py`, `tests/tools/test_shell_integration.py`.

---

### Task 1: `shell_policy.py`

**Files:** Create `.../security/shell_policy.py`; Test `tests/security/test_shell_policy.py`.

**Interfaces:** `ShellPolicyError`; `EXECUTABLE_ALLOWLIST`, `SHELL_METACHARACTERS`, `CONTROLLED_PATH`; `parse_command(command, cwd) -> ParsedCommand(argv, path_tokens)`; `validate_executable(argv) -> None`.

- [ ] **Step 1: Failing test**

```python
# apps/daemon/tests/security/test_shell_policy.py
from pathlib import Path

import pytest

from thoth_daemon.security.shell_policy import (
    ShellPolicyError,
    parse_command,
    validate_executable,
)


@pytest.mark.parametrize("cmd", ["ls; rm -rf ~", "a && b", "a | b", "echo `x`", "echo $(x)", "cat > f", "ls *.py"])
def test_metacharacters_rejected(cmd: str) -> None:
    with pytest.raises(ShellPolicyError):
        parse_command(cmd, "/tmp")


def test_empty_rejected() -> None:
    with pytest.raises(ShellPolicyError):
        parse_command("   ", "/tmp")


def test_plain_command_no_path_tokens() -> None:
    p = parse_command("git status", "/tmp")
    assert p.argv == ["git", "status"] and p.path_tokens == []


def test_flags_are_not_path_tokens() -> None:
    assert parse_command("git log --oneline", "/tmp").path_tokens == []


def test_absolute_path_arg_is_a_token(tmp_path: Path) -> None:
    p = parse_command("cat /etc/hosts", str(tmp_path))
    assert p.path_tokens == ["/etc/hosts"]


def test_relative_path_arg_resolved_against_cwd(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    p = parse_command("cat sub/x.txt", str(tmp_path))
    assert p.path_tokens == [str(tmp_path / "sub" / "x.txt")]


def test_dotdot_arg_resolves_outside(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    p = parse_command("cat ../secret", str(sub))
    assert p.path_tokens == [str(tmp_path / "secret")]


def test_validate_executable_allows_allowlisted() -> None:
    validate_executable(["git", "status"])


@pytest.mark.parametrize("argv", [["sudo", "ls"], ["rm", "-rf", "x"], ["/tmp/git", "status"], ["curl", "x"]])
def test_validate_executable_rejects(argv: list[str]) -> None:
    with pytest.raises(ShellPolicyError):
        validate_executable(argv)
```

- [ ] **Step 2: Run → fails** (module missing).

- [ ] **Step 3: Implement**

```python
# apps/daemon/src/thoth_daemon/security/shell_policy.py
"""Restricted-shell command policy (pure). The shell tool runs an allowlisted
executable via argv with NO shell interpretation; this module decides what is
allowed and extracts the paths a command touches so the ScopeEnforcer can
contain them. See docs/TOOL_CONTRACTS.md §4."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from thoth_daemon.security.paths import expand_and_resolve


class ShellPolicyError(Exception):
    pass


EXECUTABLE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "git", "ls", "cat", "head", "tail", "wc", "rg", "grep", "find", "echo",
        "pwd", "make", "uv", "python", "python3", "node", "npm", "pnpm", "pytest",
    }
)

# Rejected anywhere in the raw command (defense in depth; also structurally
# impossible because a shell is never used).
SHELL_METACHARACTERS: frozenset[str] = frozenset(";&|`$()<>*?{}\n\r")

CONTROLLED_PATH = "/usr/bin:/bin:/usr/local/bin"


@dataclass
class ParsedCommand:
    argv: list[str]
    path_tokens: list[str] = field(default_factory=list)


def _looks_like_path(token: str) -> bool:
    return "/" in token or token.startswith("~")


def parse_command(command: str, cwd: str) -> ParsedCommand:
    """Split *command* into argv and resolve the paths it references relative
    to *cwd*. Raise ShellPolicyError for empty input or shell metacharacters."""
    if not command.strip():
        raise ShellPolicyError("empty command")
    bad = sorted({c for c in command if c in SHELL_METACHARACTERS})
    if bad:
        raise ShellPolicyError(f"shell metacharacters not allowed: {''.join(bad)!r}")
    argv = shlex.split(command)
    if not argv:
        raise ShellPolicyError("empty command")
    tokens: list[str] = []
    for token in argv[1:]:
        if _looks_like_path(token):
            base = token if (token.startswith(("~", "/"))) else str(Path(cwd) / token)
            tokens.append(str(expand_and_resolve(base)))
    return ParsedCommand(argv=argv, path_tokens=tokens)


def validate_executable(argv: list[str]) -> None:
    """Raise unless argv[0] is a bare, allowlisted command name."""
    exe = argv[0]
    if "/" in exe:
        raise ShellPolicyError(f"executable must be a bare command name, not a path: {exe}")
    if exe not in EXECUTABLE_ALLOWLIST:
        raise ShellPolicyError(f"executable not allowed: {exe}")
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit** `feat(security): restricted-shell command policy (allowlist, metachar reject, path tokens)`

---

### Task 2: `ShellRun` tool

**Files:** Create `.../tools/shell_tool.py`; Test `tests/tools/test_shell_tool.py`.

**Interfaces:** `ShellRun` (R2, supports_dry_run, timeout_s=30, redaction `[stdout,stderr]`, `requested_scope -> [cwd, *path_tokens]`); `register_shell_tool(registry)`.

- [ ] **Step 1: Failing test**

```python
# apps/daemon/tests/tools/test_shell_tool.py
import asyncio
from pathlib import Path

import pytest

from thoth_daemon.tools.shell_tool import ShellRun


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
    # `ls` on a missing path exits non-zero (no metacharacters in the command).
    with pytest.raises(RuntimeError):
        await tool.run(tool.input_model(command="ls no_such_dir_here", cwd=str(tmp_path)), dry_run=False)


async def test_offlist_executable_refused(tmp_path: Path) -> None:
    tool = _tool()
    with pytest.raises(Exception):
        await tool.run(tool.input_model(command="sudo ls", cwd=str(tmp_path)), dry_run=False)


async def test_metacharacter_command_refused(tmp_path: Path) -> None:
    tool = _tool()
    with pytest.raises(Exception):
        await tool.run(tool.input_model(command="ls; echo hi", cwd=str(tmp_path)), dry_run=False)


def test_requested_scope_includes_cwd_and_path_args(tmp_path: Path) -> None:
    tool = _tool()
    scope = tool.requested_scope(tool.input_model(command="cat /etc/hosts", cwd=str(tmp_path)))
    assert str(tmp_path) in scope.paths and "/etc/hosts" in scope.paths


def test_requested_scope_metachar_falls_back_to_cwd(tmp_path: Path) -> None:
    tool = _tool()
    scope = tool.requested_scope(tool.input_model(command="ls; rm -rf ~", cwd=str(tmp_path)))
    assert scope.paths == [str(tmp_path)]  # best-effort; run() refuses it


def test_tool_contract_flags() -> None:
    tool = _tool()
    assert tool.default_risk.value == "R2"
    assert tool.supports_dry_run and tool.redaction_fields == ["stdout", "stderr"]


async def test_terminate_kills_running_process() -> None:
    proc = await asyncio.create_subprocess_exec(
        "sleep", "30", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    assert proc.returncode is None
    await ShellRun._terminate(proc)
    assert proc.returncode is not None


async def test_run_cancellation_terminates(tmp_path: Path) -> None:
    tool = _tool()
    task = asyncio.ensure_future(
        tool.run(tool.input_model(command="find /", cwd=str(tmp_path)), dry_run=False)
    )
    await asyncio.sleep(0.15)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
```

- [ ] **Step 2: Run → fails** (module missing).

- [ ] **Step 3: Implement**

```python
# apps/daemon/src/thoth_daemon/tools/shell_tool.py
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
```

- [ ] **Step 4: Run → pass.** (`test_run_cancellation_terminates` relies on `find /` running >0.15 s; if the sandbox lacks `/`, use `find <large tmp tree>`.)

- [ ] **Step 5: Commit** `feat(tools): restricted shell_run — allowlisted argv exec, R2, scoped, cancellable`

---

### Task 3: Wire app; scope + R2 approval integration

**Files:** Modify `app.py`; Test `tests/tools/test_shell_integration.py`.

- [ ] **Step 1: Failing test**

```python
# apps/daemon/tests/tools/test_shell_integration.py
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


async def test_backstop_refuses_denylisted_arg(tmp_path: Path) -> None:
    reg = ToolRegistry()
    register_shell_tool(reg)
    allowed = ResourceScope(paths=[str(Path.home())])
    result = await reg.execute(
        _inv({"command": "cat .ssh/id_rsa", "cwd": str(Path.home())}), allowed
    )
    assert not result.ok and "scope violation" in (result.error or "")
```

- [ ] **Step 2: Run → the scope cases already pass via the slice-1 backstop (regression proof); the redaction assertion confirms wiring.**

- [ ] **Step 3: Wire `app.py`** — after `register_fs_tools(registry)` add:

```python
        register_shell_tool(registry)  # restricted shell (slice 4)
```
and import `from thoth_daemon.tools.shell_tool import register_shell_tool`.

- [ ] **Step 4: Run** integration + full API suite (hang-guarded).

- [ ] **Step 5: Commit** `feat(daemon): register restricted shell_run; scope contains argument paths`

---

### Task 4: Docs, gate, live-OS verification

- [ ] **Step 1: ADR-014** (append to `docs/DECISIONS.md`) — text from spec §10.
- [ ] **Step 2: THREAT_MODEL** — T3 mitigation row: restricted shell now implemented (allowlist, no shell, arg-path containment, R2 approval, output cap, cancel).
- [ ] **Step 3: STATUS + MILESTONES** — restricted shell exists + live-verified; **keep** the no-autonomous-control statement; bump daemon test count; check "Restricted shell tool per TOOL_CONTRACTS §4".
- [ ] **Step 4: Full gate** — pytest (hang-guard), ruff, ruff format, mypy.
- [ ] **Step 5: Live-OS verification** — script in a temp dir: `git init` isn't needed; run `ls -la`, `echo hi`, `cat <file>` (real output); confirm `sudo -v`, `cat /etc/passwd`, `ls ; echo hi`, `curl x` each refused. Only then does STATUS claim the capability.
- [ ] **Step 6: Commit** `docs: ADR-014 + threat model + status for restricted shell (slice 4)`

---

## Self-Review

**Spec coverage:** §4 policy → T1; §5 tool (run/dry-run/cap/cancel) + requested_scope → T2; §5 arg containment via enforcer + §6 redaction → T3; §7 cancel → T2 (`_terminate`, cancellation); §8 tests → each task; §9 live-OS → T4; §10 ADR → T4.

**Placeholder scan:** none; ADR-014 next. Cancellation test's reliance on a slow `find /` is flagged with a fallback.

**Type consistency:** `parse_command -> ParsedCommand(argv, path_tokens)`, `validate_executable(argv)->None`, `ShellRun.requested_scope -> ResourceScope`, `_terminate(proc)->None`, `register_shell_tool(registry)->None`, output fields `command/executed/exit_code/stdout/stderr/truncated` consistent T1–T4.
