# Slice 5 — Git workflow tools (design/spec)

**Date:** 2026-07-12 · **Phase:** 3 · **Status:** approved design, pre-plan
**Depends on:** slices 1–4 (scope, auth, fs, shell), merged.
**Delivers:** dedicated typed git tools — reads at **R0** (no approval), `add`/`commit` at **R1** —
gated by the slice-1 scope enforcer. Local ops only; `git push` deferred (needs a network remote).

## 1. Why dedicated tools (not shell_run)

`git` is allowlisted in the restricted shell, but `shell_run` is **R2 (approval per command)** and
returns masked text. Common git reads (`status`, `log`, `diff`) should be **R0** with structured,
typed output and proper verification. Dedicated tools give risk granularity, structured results,
and self-verification that raw shell can't.

## 2. Goals / non-goals

**Goals**
- `git_status`, `git_log`, `git_diff` (R0), `git_add`, `git_commit` (R1) — typed I/O, scoped cwd,
  timeout, output cap, redaction, verification, unit + live-OS tests in a real temp repo.
- Reuse the slice-1 scope gate: every tool's `requested_scope` includes the repo cwd (and, for
  `git_add`, its path args) so an out-of-scope/denylisted repo or path is refused.

**Non-goals (this slice)**
- `git push`/`pull`/`fetch` (network + remote; R2; deferred to when a remote is available to verify).
- `git branch`/`checkout`/`reset`/`rebase`/`merge` (state-mutating history ops; a later slice).
- Replacing `shell_run` for git — it remains available for anything these tools don't cover.

## 3. Components

| File | New? | Responsibility |
|---|---|---|
| `apps/daemon/src/omnimac_daemon/tools/git_io.py` | new | `run_git(cwd, args, timeout) -> GitResult(code, stdout, stderr)` — subprocess exec, controlled PATH, `stdin=DEVNULL`, output cap. Pure I/O. |
| `apps/daemon/src/omnimac_daemon/tools/git_tools.py` | new | the five tools + `register_git_tools(registry)`. |
| `apps/daemon/src/omnimac_daemon/app.py` | edit | `register_git_tools(registry)`. |
| `docs/DECISIONS.md`, `docs/STATUS.md`, `docs/MILESTONES.md` | edit | ADR-015, status. |

Reuses: `security/shell_policy.CONTROLLED_PATH`, `security/paths.expand_and_resolve`, the
`ScopeEnforcer` gate + backstop, R1 approval flow.

## 4. `git_io.py`

`run_git(cwd: Path, args: list[str], timeout: float = 30.0) -> GitResult`:
- `create_subprocess_exec("git", *args, cwd=str(cwd), stdin=DEVNULL, stdout=PIPE, stderr=PIPE,
  env={"PATH": CONTROLLED_PATH, "HOME": str(expand_and_resolve("~"))})`.
- `await asyncio.wait_for(proc.communicate(), timeout)`; on timeout terminate→kill, raise.
- cap stdout/stderr at 64 KiB; decode UTF-8 `errors="replace"`.
- returns `GitResult(returncode, stdout, stderr, truncated)`. Never raises for non-zero exit — the
  tool decides what a non-zero code means.

## 5. Tools

All: `input_model` has `cwd: str`; `requested_scope` includes `cwd` (resolved via the enforcer);
`run()` resolves cwd and requires it be a directory. `git` errors (exit ≠ 0) that mean failure
raise `RuntimeError(stderr)` → `ok=False` → verification fails.

| Tool | Risk | Verify | In → Out |
|---|---|---|---|
| `git_status` | R0 | NONE_READONLY | `{cwd}` → `{cwd, branch, staged[], unstaged[], untracked[], clean}` |
| `git_log` | R0 | NONE_READONLY | `{cwd, max_count=20}` → `{cwd, commits:[{sha, subject, author}]}` |
| `git_diff` | R0 | NONE_READONLY | `{cwd, staged=False}` → `{cwd, diff, truncated}` · `redaction_fields=["diff"]` |
| `git_add` | R1 | STATE_PROBE | `{cwd, paths[]}` → `{cwd, added[]}` |
| `git_commit` | R1 | STATE_PROBE | `{cwd, message}` → `{cwd, sha, message}` |

- **`git_status`**: `git status --porcelain=v1 --branch`. Parse the `## <branch>...` line for
  `branch`; XY codes → staged (index col ≠ space/`?`), unstaged (worktree col ≠ space), untracked
  (`??`). `clean = not (staged or unstaged or untracked)`. Non-repo cwd → git exits ≠ 0 → raise.
- **`git_log`**: `git log --max-count=N --pretty=format:%H%x1f%s%x1f%an` (unit-separator split);
  empty repo (no commits) → returns `commits: []` (git exits ≠ 0 with "does not have any commits";
  treat that specific case as empty, else raise).
- **`git_diff`**: `git diff` or `git diff --cached`. `diff` redacted in the record (may contain
  secrets), same rationale as fs content / shell stdout.
- **`git_add`**: `requested_scope = [cwd, *resolved(paths)]` (best-effort resolve against cwd) so the
  enforcer refuses out-of-scope/denylisted path args. `git add -- <paths>`; then self-verify with
  `git status --porcelain` that each path is staged, else raise.
- **`git_commit`**: `git commit -m <message>`; nothing staged → git exits ≠ 0 → raise. Then
  `git rev-parse HEAD` → `sha`; self-verify the commit exists. Message is passed as a single argv
  element (no shell), so it can contain spaces safely.

## 6. Redaction & residual risk

`git_diff.diff` is a redaction field (masked in audit/logs/WS). File paths (status/add) and commit
subjects (log) are not secrets and stay visible. Residual (documented): a secret in a commit
`message` argument is recorded; mitigated because commit is R1 in a trusted workspace and the
message is user-authored.

## 7. Testing (TDD, real temp git repo)

- **`git_io.py`**: `run_git` on a temp repo returns real output; non-zero code captured, not raised;
  timeout terminates.
- **Tools (real repo)**: init a temp repo (`run_git(tmp, ["init"])`, set user.email/name), write a
  file → `git_status` shows it untracked & `clean=False`; `git_add` stages it (verified);
  `git_commit` returns a real sha (verified via rev-parse); `git_log` lists it; `git_diff --cached`
  shows the staged patch; a fresh (no-commit) repo → `git_log` returns `[]`.
- **Scope**: `git_status` on an out-of-scope cwd → backstop `scope violation`; `git_add` of an
  out-of-scope path arg → refused; denylisted cwd/path refused.
- **Regression**: full suite green; mocks/fs/shell untouched.

## 8. Live-OS verification

Script: real temp repo, `git_status`→`git_add`→`git_commit`→`git_log`→`git_diff` all against real
git, printing real (unredacted-in-tool) structured results; confirm an out-of-scope cwd and a
denylisted path are refused. Only then does STATUS claim the capability.

## 9. ADR

**ADR-015:** dedicated git tools wrap `git` via `run_git` (subprocess, controlled PATH, `stdin=DEVNULL`,
output cap) with typed structured output; reads R0, `add`/`commit` R1; `requested_scope` puts the
repo cwd (and add's path args) under the slice-1 enforcer (no new policy code); `add`/`commit`
self-verify (staged check / `rev-parse`); `diff` redacted. Push/history-mutating ops deferred.
Chosen over routing git through `shell_run` (R2-always, unstructured, masked).
