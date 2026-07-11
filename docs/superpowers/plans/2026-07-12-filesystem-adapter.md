# Filesystem Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or subagent-driven-development). Steps use checkbox (`- [ ]`).

**Goal:** Real, scoped `fs_read_file`/`fs_list_dir`/`fs_write_file`/`fs_stat` tools — THOTH's first real disk access — gated automatically by slice-1 scope enforcement.

**Architecture:** Pure byte helpers (`fs_io.py`) under typed `ToolDefinition`s (`fs_tools.py`) that declare `requested_scope(paths=[path])`. Writes are atomic (temp + `os.replace`) and self-verified by read-back. Content is a redaction field. Tools are added alongside the mocks and registered in `app.py`.

**Tech Stack:** Python 3.12, Pydantic v2, pytest + pytest-asyncio.

## Global Constraints

- mypy strict + ruff clean. All inputs `extra="forbid"`.
- Tools resolve paths with `security.paths.expand_and_resolve` before I/O (same resolver the enforcer uses).
- No new policy code — scope is enforced by the slice-1 gate + backstop via `requested_scope`.
- Existing 300 daemon + 46 desktop tests stay green (fs tools are additive; mocks untouched).
- Branch `phase-3/filesystem-adapter`. Commit trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (second `-m`). No push. No control overclaim in docs.

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `apps/daemon/src/thoth_daemon/tools/fs_io.py` | Create | `read_text_capped`, `atomic_write`, `BinaryFileError`. |
| `apps/daemon/src/thoth_daemon/tools/fs_tools.py` | Create | 4 tools + `register_fs_tools`. |
| `apps/daemon/src/thoth_daemon/app.py` | Modify | `register_fs_tools(registry)`. |
| `docs/DECISIONS.md`, `docs/STATUS.md`, `docs/MILESTONES.md` | Modify | ADR-013, status. |

Tests: `tests/tools/test_fs_io.py`, `test_fs_tools.py`, `test_fs_integration.py`.

---

### Task 1: Byte helpers (`fs_io.py`)

**Files:** Create `apps/daemon/src/thoth_daemon/tools/fs_io.py`; Test `apps/daemon/tests/tools/test_fs_io.py`.

**Interfaces:** `read_text_capped(path: Path, max_bytes: int) -> tuple[str, int, bool]`; `atomic_write(path: Path, data: bytes) -> None`; `class BinaryFileError(ValueError)`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/tools/test_fs_io.py
from pathlib import Path

import pytest

from thoth_daemon.tools.fs_io import BinaryFileError, atomic_write, read_text_capped


def test_read_small_file_not_truncated(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("hello world")
    text, n, truncated = read_text_capped(p, 1024)
    assert text == "hello world" and n == 11 and truncated is False


def test_read_over_cap_is_truncated(tmp_path: Path) -> None:
    p = tmp_path / "big.txt"
    p.write_text("x" * 100)
    text, n, truncated = read_text_capped(p, 10)
    assert len(text) == 10 and n == 10 and truncated is True


def test_read_utf8_multibyte_at_boundary(tmp_path: Path) -> None:
    p = tmp_path / "u.txt"
    p.write_bytes(("a" * 9 + "é").encode("utf-8"))  # 'é' = 2 bytes, straddles a 10-byte cap
    text, n, truncated = read_text_capped(p, 10)
    assert text == "a" * 9 and truncated is True  # partial char trimmed


def test_read_binary_raises(tmp_path: Path) -> None:
    p = tmp_path / "b.bin"
    p.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(BinaryFileError):
        read_text_capped(p, 1024)


def test_atomic_write_creates_exact_bytes_no_temp_left(tmp_path: Path) -> None:
    p = tmp_path / "out.txt"
    atomic_write(p, b"payload")
    assert p.read_bytes() == b"payload"
    assert [c.name for c in tmp_path.iterdir()] == ["out.txt"]  # no temp leftover


def test_atomic_write_overwrites(tmp_path: Path) -> None:
    p = tmp_path / "o.txt"
    p.write_text("old")
    atomic_write(p, b"new")
    assert p.read_bytes() == b"new"


def test_atomic_write_missing_parent_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        atomic_write(tmp_path / "nope" / "x.txt", b"data")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/tools/test_fs_io.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```python
# apps/daemon/src/thoth_daemon/tools/fs_io.py
"""Low-level filesystem byte helpers for the fs tools: a size-capped UTF-8
read and an atomic write. Operate on already-scope-validated paths."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


class BinaryFileError(ValueError):
    """A file is not decodable as UTF-8 text."""


def read_text_capped(path: Path, max_bytes: int) -> tuple[str, int, bool]:
    """Return (text, byte_count, truncated). Read at most *max_bytes*; set
    truncated when the file is larger. Raise BinaryFileError for non-UTF-8
    bytes (after trimming up to 3 trailing bytes at a truncation boundary)."""
    with open(path, "rb") as f:
        raw = f.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    data = raw[:max_bytes] if truncated else raw
    try:
        return data.decode("utf-8"), len(data), truncated
    except UnicodeDecodeError:
        if truncated:
            for trim in range(1, 4):  # a multibyte char may straddle the cap
                try:
                    return data[:-trim].decode("utf-8"), len(data), True
                except UnicodeDecodeError:
                    continue
        raise BinaryFileError(f"{path} is not valid UTF-8 text") from None


def atomic_write(path: Path, data: bytes) -> None:
    """Write *data* to *path* atomically: temp file in the same directory,
    fsync, then os.replace. Parent must already exist."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".thoth-tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/tools/test_fs_io.py -q` → PASS (7).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/thoth_daemon/tools/fs_io.py apps/daemon/tests/tools/test_fs_io.py
git commit -m "feat(tools): fs byte helpers — capped UTF-8 read, atomic write" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Read tools (`fs_read_file`, `fs_list_dir`, `fs_stat`)

**Files:** Create `apps/daemon/src/thoth_daemon/tools/fs_tools.py`; Test `apps/daemon/tests/tools/test_fs_tools.py`.

**Interfaces:** `FsReadFile`, `FsListDir`, `FsStat` (`ToolDefinition`s, R0, NONE_READONLY, `requested_scope(paths=[path])`).

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/tools/test_fs_tools.py
from pathlib import Path

import pytest

from thoth_daemon.tools.fs_tools import FsListDir, FsReadFile, FsStat


async def test_fs_read_file_reads_real_content(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("hello")
    out = await FsReadFile().run(FsReadFile().input_model(path=str(p)), dry_run=False)
    assert out.content == "hello" and out.bytes == 5 and out.truncated is False


async def test_fs_read_file_binary_raises(tmp_path: Path) -> None:
    p = tmp_path / "b.bin"
    p.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError):
        await FsReadFile().run(FsReadFile().input_model(path=str(p)), dry_run=False)


async def test_fs_list_dir_lists_entries(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "f.txt").write_text("x")
    out = await FsListDir().run(FsListDir().input_model(path=str(tmp_path)), dry_run=False)
    by_name = {e.name: e.is_dir for e in out.entries}
    assert by_name == {"sub": True, "f.txt": False}


async def test_fs_list_dir_on_file_raises(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_text("x")
    with pytest.raises(NotADirectoryError):
        await FsListDir().run(FsListDir().input_model(path=str(p)), dry_run=False)


async def test_fs_stat_existing_and_missing(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_text("abc")
    out = await FsStat().run(FsStat().input_model(path=str(p)), dry_run=False)
    assert out.exists and out.is_file and out.size == 3
    missing = await FsStat().run(FsStat().input_model(path=str(tmp_path / "nope")), dry_run=False)
    assert missing.exists is False


def test_read_tools_declare_scope_and_redaction() -> None:
    tool = FsReadFile()
    scope = tool.requested_scope(tool.input_model(path="~/x"))
    assert scope.paths == ["~/x"]
    assert "content" in FsReadFile.redaction_fields
```

- [ ] **Step 2: Run to verify it fails** → module missing.

- [ ] **Step 3: Implement** (create `fs_tools.py` with the shared bases + the three read tools; the write tool is Task 3)

```python
# apps/daemon/src/thoth_daemon/tools/fs_tools.py
"""Real, scoped filesystem tools (Phase 3 slice 3). Unlike the mocks these
touch the actual disk — but only within approved scope, enforced by the
ScopeEnforcer gate + registry backstop via requested_scope()."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from thoth_daemon.schemas import ResourceScope, RiskLevel, VerificationStrategy
from thoth_daemon.security.paths import expand_and_resolve
from thoth_daemon.tools.base import ToolDefinition
from thoth_daemon.tools.fs_io import atomic_write, read_text_capped
from thoth_daemon.tools.registry import ToolRegistry


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FsReadFileIn(_In):
    path: str
    max_bytes: int = Field(default=1_048_576, gt=0)


class FsReadFileOut(_Out):
    path: str
    content: str
    bytes: int
    truncated: bool


class FsReadFile(ToolDefinition[FsReadFileIn, FsReadFileOut]):
    name = "fs_read_file"
    description = "Read an approved text file from disk (scoped, size-capped)."
    input_model = FsReadFileIn
    output_model = FsReadFileOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY
    redaction_fields: ClassVar[list[str]] = ["content"]

    def requested_scope(self, args: FsReadFileIn) -> ResourceScope:  # type: ignore[override]
        return ResourceScope(paths=[args.path])

    async def run(self, args: FsReadFileIn, dry_run: bool) -> FsReadFileOut:
        p = expand_and_resolve(args.path)
        text, n, truncated = read_text_capped(p, args.max_bytes)
        return FsReadFileOut(path=str(p), content=text, bytes=n, truncated=truncated)


class FsEntry(_Out):
    name: str
    is_dir: bool


class FsListDirIn(_In):
    path: str


class FsListDirOut(_Out):
    path: str
    entries: list[FsEntry]


class FsListDir(ToolDefinition[FsListDirIn, FsListDirOut]):
    name = "fs_list_dir"
    description = "List an approved directory from disk (scoped)."
    input_model = FsListDirIn
    output_model = FsListDirOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def requested_scope(self, args: FsListDirIn) -> ResourceScope:  # type: ignore[override]
        return ResourceScope(paths=[args.path])

    async def run(self, args: FsListDirIn, dry_run: bool) -> FsListDirOut:
        p = expand_and_resolve(args.path)
        if not p.is_dir():
            raise NotADirectoryError(f"{p} is not a directory")
        entries: list[FsEntry] = []
        for child in sorted(p.iterdir(), key=lambda c: c.name):
            try:
                entries.append(FsEntry(name=child.name, is_dir=child.is_dir()))
            except OSError:
                continue
        return FsListDirOut(path=str(p), entries=entries)


class FsStatIn(_In):
    path: str


class FsStatOut(_Out):
    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size: int


class FsStat(ToolDefinition[FsStatIn, FsStatOut]):
    name = "fs_stat"
    description = "Stat an approved path (existence/type/size); read-only probe."
    input_model = FsStatIn
    output_model = FsStatOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def requested_scope(self, args: FsStatIn) -> ResourceScope:  # type: ignore[override]
        return ResourceScope(paths=[args.path])

    async def run(self, args: FsStatIn, dry_run: bool) -> FsStatOut:
        p = expand_and_resolve(args.path)
        if not p.exists():
            return FsStatOut(path=str(p), exists=False, is_file=False, is_dir=False, size=0)
        return FsStatOut(
            path=str(p), exists=True, is_file=p.is_file(), is_dir=p.is_dir(), size=p.stat().st_size
        )


def register_fs_tools(registry: ToolRegistry) -> None:
    for tool in (FsReadFile(), FsListDir(), FsWriteFile(), FsStat()):
        registry.register(tool)
```
(NOTE: `register_fs_tools` references `FsWriteFile`, added in Task 3. Add the write tool before running `register_fs_tools` anywhere; the read-tool tests above don't call it, so Task 2 tests pass. If running Task 2 in isolation, temporarily omit `FsWriteFile()` from the tuple, then restore in Task 3. Simpler: implement Task 3's `FsWriteFile` class in the same file now and only its tests come in Task 3.)

To keep tasks independently green, **add the `FsWriteFile` class body in this step too** (code identical to Task 3 Step 3) so `register_fs_tools` resolves; Task 3 only adds its tests + wiring.

- [ ] **Step 4: Run to verify pass** → `pytest apps/daemon/tests/tools/test_fs_tools.py -q` PASS (6).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/thoth_daemon/tools/fs_tools.py apps/daemon/tests/tools/test_fs_tools.py
git commit -m "feat(tools): scoped fs_read_file/fs_list_dir/fs_stat over real disk" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Write tool (`fs_write_file`)

**Files:** Modify `fs_tools.py` (add `FsWriteFile` if not already present in Task 2); Test add to `test_fs_tools.py`.

**Interfaces:** `FsWriteFile` (R1, STATE_PROBE, `supports_dry_run=True`, `requested_scope(paths=[path])`).

- [ ] **Step 1: Write the failing test** (append to `test_fs_tools.py`)

```python
async def test_fs_write_creates_file(tmp_path: Path) -> None:
    from thoth_daemon.tools.fs_tools import FsWriteFile

    p = tmp_path / "w.txt"
    tool = FsWriteFile()
    out = await tool.run(tool.input_model(path=str(p), content="data"), dry_run=False)
    assert out.written is True and out.bytes == 4
    assert p.read_text() == "data"


async def test_fs_write_dry_run_writes_nothing(tmp_path: Path) -> None:
    from thoth_daemon.tools.fs_tools import FsWriteFile

    p = tmp_path / "w.txt"
    tool = FsWriteFile()
    out = await tool.run(tool.input_model(path=str(p), content="data"), dry_run=True)
    assert out.written is False and out.bytes == 4
    assert not p.exists()


async def test_fs_write_overwrites(tmp_path: Path) -> None:
    from thoth_daemon.tools.fs_tools import FsWriteFile

    p = tmp_path / "w.txt"
    p.write_text("old")
    tool = FsWriteFile()
    await tool.run(tool.input_model(path=str(p), content="new"), dry_run=False)
    assert p.read_text() == "new"


async def test_fs_write_missing_parent_fails(tmp_path: Path) -> None:
    from thoth_daemon.tools.fs_tools import FsWriteFile

    tool = FsWriteFile()
    with pytest.raises(FileNotFoundError):
        await tool.run(tool.input_model(path=str(tmp_path / "no" / "w.txt"), content="x"), dry_run=False)
```

- [ ] **Step 2: Run to verify it fails** (if `FsWriteFile` wasn't added in Task 2) or passes-then-augments. If added in Task 2, this step confirms behavior directly.

- [ ] **Step 3: Implement** (the `FsWriteFile` class — place in `fs_tools.py` after `FsReadFile`)

```python
class FsWriteFileIn(_In):
    path: str
    content: str


class FsWriteFileOut(_Out):
    path: str
    written: bool
    bytes: int


class FsWriteFile(ToolDefinition[FsWriteFileIn, FsWriteFileOut]):
    name = "fs_write_file"
    description = "Write/overwrite an approved file (scoped, atomic, self-verified)."
    input_model = FsWriteFileIn
    output_model = FsWriteFileOut
    default_risk = RiskLevel.R1
    supports_dry_run = True
    verification = VerificationStrategy.STATE_PROBE
    redaction_fields: ClassVar[list[str]] = ["content"]

    def requested_scope(self, args: FsWriteFileIn) -> ResourceScope:  # type: ignore[override]
        return ResourceScope(paths=[args.path])

    async def run(self, args: FsWriteFileIn, dry_run: bool) -> FsWriteFileOut:
        p = expand_and_resolve(args.path)
        data = args.content.encode("utf-8")
        if dry_run:
            return FsWriteFileOut(path=str(p), written=False, bytes=len(data))
        atomic_write(p, data)
        if p.read_bytes() != data:  # read-back self-verification (real state probe)
            raise OSError(f"write verification failed for {p}")
        return FsWriteFileOut(path=str(p), written=True, bytes=len(data))
```

- [ ] **Step 4: Run to verify pass** → `pytest apps/daemon/tests/tools/test_fs_tools.py -q` PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/thoth_daemon/tools/fs_tools.py apps/daemon/tests/tools/test_fs_tools.py
git commit -m "feat(tools): scoped atomic fs_write_file with read-back self-verification" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Wire into app; scope enforcement over the real filesystem

**Files:** Modify `apps/daemon/src/thoth_daemon/app.py`; Test `apps/daemon/tests/tools/test_fs_integration.py`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/tools/test_fs_integration.py
from pathlib import Path

from thoth_daemon.core.scope import ScopeEnforcer, ScopeViolation
from thoth_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation
from thoth_daemon.tools.fs_tools import FsReadFile, register_fs_tools
from thoth_daemon.tools.registry import ToolRegistry


def _inv(name: str, args: dict) -> ToolInvocation:
    return ToolInvocation(
        task_id="t", step_id="s", tool_name=name, arguments=args, effective_risk=RiskLevel.R0
    )


async def test_registry_backstop_allows_in_scope_read(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hi")
    reg = ToolRegistry()
    register_fs_tools(reg)
    allowed = ResourceScope(paths=[str(tmp_path)])
    result = await reg.execute(_inv("fs_read_file", {"path": str(tmp_path / "a.txt")}), allowed)
    assert result.ok
    assert result.output is not None and result.output["content"] == "[REDACTED]"  # content masked


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
```

- [ ] **Step 2: Run to verify it fails** → `register_fs_tools` import ok but backstop-with-scope behavior asserts; the symlink/out-of-scope cases already pass via slice-1 backstop, the redaction assertion confirms wiring. (If all pass immediately, that's acceptable — it proves the slice-1 gate already covers real fs tools; keep the test as regression.)

- [ ] **Step 3: Wire `app.py`**

Change the registry construction in the lifespan so fs tools are registered:

```python
        registry = build_registry()
        register_fs_tools(registry)
        app.state.orchestrator = Orchestrator(
            registry=registry,
            ...
        )
```
and add the import:
```python
from thoth_daemon.tools.fs_tools import register_fs_tools
```

- [ ] **Step 4: Run** → `pytest apps/daemon/tests/tools/test_fs_integration.py -q` PASS; then full API suite (hang-guarded) to confirm the app still boots with the extra tools.

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/thoth_daemon/app.py apps/daemon/tests/tools/test_fs_integration.py
git commit -m "feat(daemon): register real fs tools; scope enforcement over the real filesystem" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Docs, full gate, live-OS verification

- [ ] **Step 1: ADR-013** — append to `docs/DECISIONS.md`:

```markdown
## ADR-013: Real filesystem tools added behind the scope contract
**Date:** 2026-07-12 · **Status:** Accepted
`fs_read_file`, `fs_list_dir`, `fs_write_file`, `fs_stat` are added (not replacing the mocks) as typed `ToolDefinition`s that declare `requested_scope(paths=[path])`, so the slice-1 `ScopeEnforcer` gate + registry backstop enforce them with no new policy code. Writes are atomic (temp file + `os.replace` in the same dir) and self-verified by read-back; `content` is a redaction field so file contents never persist to SQLite/logs/WS. Deletion/move/copy deferred to the destructive-action review in later slices. End-to-end goal→plan→read awaits the claude-agent-sdk planner (slice 8); the capability is proven now via unit + orchestrator + live-OS tests.
```

- [ ] **Step 2: STATUS + MILESTONES** — note the first real capability (scoped filesystem) exists and is verified against the real OS; **keep** "THOTH cannot control the computer" (one scoped capability ≠ control). Bump the daemon test count. Add a MILESTONES slice-3 line and check "Filesystem adapter with approved-directory scoping".

- [ ] **Step 3: Full gate**

```bash
uv run --project apps/daemon pytest apps/daemon/tests -q       # hang-guard if run bare
uv run --project apps/daemon ruff check apps/daemon && uv run --project apps/daemon ruff format --check apps/daemon
uv run --project apps/daemon mypy apps/daemon/src
```

- [ ] **Step 4: Live-OS verification** — a real script (temp workspace):

```bash
# via a short python -c using the registry with an allowed scope = temp dir:
# 1) fs_write_file writes "hello" -> file exists with exact bytes
# 2) fs_read_file reads it back
# 3) fs_list_dir shows it; fs_stat reports size
# 4) fs_read_file on ~/.ssh/id_rsa and on an out-of-root path -> refused (scope violation)
```
Only after this passes does STATUS say the filesystem capability is real and verified.

- [ ] **Step 5: Commit**

```bash
git add docs/DECISIONS.md docs/STATUS.md docs/MILESTONES.md
git commit -m "docs: ADR-013 + status for real filesystem adapter (slice 3)" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** §4 tools → T2/T3; §5 redaction → T2 (redaction_fields) + T4 (masked-in-output assertion); §6 scope safety → T4; §7 tests → each task; §8 live-OS → T5 Step 4; §9 ADR → T5.

**Placeholder scan:** none; ADR number 013 confirmed next. The Task 2/3 ordering note (add `FsWriteFile` in Task 2 so `register_fs_tools` resolves) is called out explicitly.

**Type consistency:** `read_text_capped -> tuple[str,int,bool]`, `atomic_write(path,data)->None`, each tool `requested_scope(args)->ResourceScope`, `register_fs_tools(registry)->None`, output fields (`content/bytes/truncated`, `entries[name,is_dir]`, `written/bytes`, `exists/is_file/is_dir/size`) consistent across tasks.
