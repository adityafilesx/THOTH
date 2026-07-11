# Slice 3 — Filesystem adapter (design/spec)

**Date:** 2026-07-12 · **Phase:** 3 · **Status:** approved design, pre-plan
**Depends on:** slices 1 (scope enforcement) + 2 (auth), both merged.
**Delivers:** THOTH's **first real capability** — scoped read/list/write/stat of the real filesystem.

## 1. Context & problem

Slices 1–2 built the safety backbone (scope enforcement, auth) but every tool is still an
in-memory mock. This slice adds the first tools that touch the **real disk**. Because they
declare `requested_scope`, the slice-1 gate (orchestrator pre-EXECUTING) and registry backstop
enforce them automatically — a real read/write can only hit an approved root and never a
denylisted credential/system path. This is where "verify against the real OS" starts being
literal.

## 2. Goals / non-goals

**Goals**
- Real, typed, scoped filesystem tools: `fs_read_file`, `fs_list_dir`, `fs_write_file`, `fs_stat`.
- Every tool satisfies the full TOOL_CONTRACTS §1 contract (typed I/O, risk, timeout,
  cancellation, dry-run where it mutates, verification, resource scope, redaction, unit tests).
- Writes are **atomic** and **self-verified** (read-back) so success is never merely "no exception".
- **Real-OS verification**: tests exercise real files/dirs in temp locations, and prove
  out-of-scope / denylisted / symlink-escape paths are refused against the real filesystem.

**Non-goals (this slice)**
- Delete/move/copy (`fs_delete`, `fs_move`) — deletion is R2/R3-shaped and belongs with the
  shell/git slices' destructive-action review; not needed for the first capability.
- Wiring a real goal→plan→read end to end — the deterministic mock planner does not emit these
  tools; that arrives with the claude-agent-sdk planner (slice 8). Proven here via unit tests +
  a direct orchestrator test with a custom one-step planner.
- Replacing the mock tools — the safety-core tests and the mock planner keep using mocks; the
  real fs tools are **added** alongside.
- Refactoring the VerificationEngine's `STATE_PROBE` (still a placeholder); `fs_write_file`
  self-verifies via read-back instead (noted for a future probe-tool enhancement).

## 3. Components

| File | New? | Responsibility |
|---|---|---|
| `apps/daemon/src/thoth_daemon/tools/fs_tools.py` | new | The four fs `ToolDefinition`s + `register_fs_tools(registry)`. |
| `apps/daemon/src/thoth_daemon/tools/fs_io.py` | new | Small pure helpers: capped UTF-8 read, atomic write. (Keeps `fs_tools.py` about contracts, `fs_io.py` about bytes.) |
| `apps/daemon/src/thoth_daemon/app.py` | edit | `register_fs_tools(registry)` after `build_registry()`. |
| `docs/DECISIONS.md`, `docs/STATUS.md`, `docs/MILESTONES.md` | edit | ADR, truthful status. |

Reuses unchanged: `security/paths.py` (`expand_and_resolve`, denylist), the `ScopeEnforcer`
gate + backstop, `ToolDefinition.requested_scope`.

## 4. Tool contracts

All inputs `extra="forbid"`. Each tool's `requested_scope(args)` returns
`ResourceScope(paths=[args.path])`, so scope + denylist enforcement is automatic. Paths are
resolved with `expand_and_resolve` (the same symlink-safe resolver the enforcer uses) before
any I/O, so the tool operates on the exact path that was validated.

| Tool | Risk | Verify | dry_run | In → Out |
|---|---|---|---|---|
| `fs_read_file` | R0 | NONE_READONLY | n/a | `{path, max_bytes=1048576}` → `{path, content, bytes, truncated}` |
| `fs_list_dir` | R0 | NONE_READONLY | n/a | `{path}` → `{path, entries: [{name, is_dir}]}` |
| `fs_write_file` | R1 | STATE_PROBE | yes | `{path, content}` → `{path, written, bytes}` |
| `fs_stat` | R0 | NONE_READONLY | n/a | `{path}` → `{path, exists, is_file, is_dir, size}` |

**`fs_read_file`**: read up to `max_bytes` (default 1 MiB); `truncated=True` if the file is
larger. Decode UTF-8; a genuine binary file (undecodable, not a truncation-boundary artifact)
raises `ValueError` → typed failed `ToolResult`. Truncation at a multibyte boundary trims up to
3 trailing bytes and retries before deciding it is binary.

**`fs_list_dir`**: target must be a directory (else raise); entries sorted by name, each with
`is_dir`; an entry that fails to stat is skipped (not fatal).

**`fs_write_file`**: `dry_run` returns `{written: False, bytes: len(utf8)}` and touches nothing.
Real: write to a temp file in the **same directory** (stays in scope), `fsync`, `os.replace`
onto the target (atomic on POSIX), then **read the target back** and assert bytes + content
match — mismatch raises. Parent directory must already exist and be in scope (no implicit
`mkdir -p`, which would silently widen the touched area).

**`fs_stat`**: never raises for a missing path — returns `exists=False`. Used as a read-only
probe.

## 5. Redaction

File contents can contain secrets, so `fs_read_file`/`fs_write_file` declare
**`redaction_fields = ["content"]`**. `registry.execute` applies redaction at one boundary that
feeds both the audit store and the WS emit, so `content` is masked in SQLite, JSONL logs, and
the event stream — satisfying invariant 7 (no secrets persisted). Consequence: the **live UI
also sees `content` masked** in this slice. That is the safe default now — there is no
content-surfacing UI yet, and the denylist already blocks credential files but not arbitrary
secrets inside approved files. Surfacing real content to the user later needs a separate
non-persisted channel; explicitly **deferred**, not solved here.

Because output is redacted at the registry boundary, **content-correctness tests call
`tool.run(args, dry_run=…)` directly** (pre-redaction) to assert real bytes; scope/redaction and
end-to-end tests go through `registry.execute` / the orchestrator and assert on status, not
content. `fs_write_file`'s read-back self-verification also runs inside `run()`, before
redaction, so it validates the real bytes.

## 6. Scope & safety (inherited, re-verified)

- In-scope path → allowed; outside every approved root → `ScopeViolation` → step FAILED
  pre-EXECUTING, never runs. Enforced by slice 1; re-tested here against the **real** filesystem.
- Denylisted path (`~/.ssh`, `.env`, `*.pem`, …) → refused even inside an approved root.
- A symlink inside an approved root pointing outside → resolves outside → refused.
- The registry backstop refuses out-of-scope even on a direct call.
- No execution outside EXECUTING; no risk downgrade; append-only audit; redaction — all unchanged.

## 7. Testing strategy (TDD, real filesystem)

- **`fs_io.py`**: capped read returns full small file; `truncated` on an over-cap file; UTF-8
  multibyte at the boundary handled; binary → raises. Atomic write creates the file with exact
  bytes; overwrites atomically; leaves no temp file behind on success.
- **`fs_read_file`**: reads a real temp file; truncates over-cap; binary file → failed result.
- **`fs_list_dir`**: lists a real temp dir (dirs + files, `is_dir` correct); non-dir → failed.
- **`fs_write_file`**: dry-run writes nothing (file absent afterwards); real write creates exact
  content; overwrite replaces; read-back mismatch path (simulate) → failed; parent-missing → failed.
- **`fs_stat`**: existing file/dir/missing.
- **Scope integration** (real FS, through the orchestrator with a custom one-step planner +
  a `scope_provider` allowing a temp root): in-scope read COMPLETES and returns real content;
  out-of-scope path → FAILED, `scope.denied`, never EXECUTING, file untouched; denylisted path →
  FAILED; symlink-escape → FAILED.
- **Backstop**: `registry.execute(fs_read invocation, allowed_scope=<temp root>)` in-scope ok,
  out-of-scope refused.
- **Regression**: full existing suite stays green (mocks untouched; fs tools are additive).

## 8. Live-OS verification (before claiming it works)

A scripted smoke test against a temp workspace: write a file via `fs_write_file`, read it back
via `fs_read_file`, list the dir, stat it — all through the registry with a real allowed scope —
and confirm a write to `~/.ssh/x` and to an out-of-root path are refused. Only after this passes
does STATUS record a *real, verified* filesystem capability (still not full computer control).

## 9. ADR

**ADR-013:** real filesystem tools are added (not replacing mocks) behind the existing
`ToolDefinition`/`requested_scope` contract, so slice-1 scope enforcement gates them with no new
policy code; writes are atomic (temp + `os.replace`) and self-verified by read-back; `content`
is a redaction field. Deletion/move deferred to the destructive-action review in later slices.
