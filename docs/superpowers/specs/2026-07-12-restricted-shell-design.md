# Slice 4 — Restricted shell tool (design/spec)

**Date:** 2026-07-12 · **Phase:** 3 · **Status:** approved design, pre-plan
**Depends on:** slices 1–3 (scope, auth, filesystem), merged.
**Risk:** highest in the system — the only tool that accepts a command string. Default risk **R2**
(explicit single-use approval per command, decided by the user).

## 1. Threat & design stance

The restricted shell must satisfy TOOL_CONTRACTS §4. The core stance: **it is not really a shell.**
Commands run via `create_subprocess_exec` (`shell=False`) after `shlex.split`, so `;`, `&&`, `|`,
backticks, `$( )`, redirection, and globs are never interpreted — and a command *containing* any
of those metacharacters is rejected outright (defense in depth). Only allowlisted executables run;
`sudo`/`rm`/anything off-list is refused. Every path the command touches (cwd + path-like args) is
scope-checked by the slice-1 enforcer, closing argument-based escapes like `cat /etc/passwd`.

## 2. Goals / non-goals

**Goals**
- One tool, `shell_run`, default **R2**, that executes an allowlisted binary with argv (no shell),
  in an approved cwd, with timeout, output cap, redaction, audit, and cooperative cancellation.
- Argument-path containment: any argv token that denotes a path must resolve inside approved scope
  and outside the denylist — enforced by the existing `ScopeEnforcer` via `requested_scope`.
- Full TDD incl. rejected paths (metachars, off-list exec, `sudo`, out-of-scope arg/cwd,
  denylisted path, broad-delete), and **live-OS verification** of a real allowlisted command.

**Non-goals (this slice)**
- Deletion/move (`rm`, `mv`) — not allowlisted; destructive-file review is later.
- A read-only/mutating split of shell risk — R2 for everything this slice (chosen).
- Pre-approval allowlist/metachar rejection at the orchestrator gate — those checks live in
  `run()` (post-approval, pre-spawn); a disallowed command is approved-then-refused, never executed.
  A gate-time `validate()` hook is a noted future enhancement.
- Live output surfacing to the UI — `stdout`/`stderr` are redaction fields (see §6).

## 3. Components

| File | New? | Responsibility |
|---|---|---|
| `apps/daemon/src/thoth_daemon/security/shell_policy.py` | new | `EXECUTABLE_ALLOWLIST`, `SHELL_METACHARACTERS`, `parse_command(command, cwd) -> ParsedCommand`, `validate_executable(argv)`; `ShellPolicyError`. Pure. |
| `apps/daemon/src/thoth_daemon/tools/shell_tool.py` | new | `ShellRun` tool + `register_shell_tool(registry)`. |
| `apps/daemon/src/thoth_daemon/app.py` | edit | `register_shell_tool(registry)`. |
| `docs/DECISIONS.md`, `docs/STATUS.md`, `docs/MILESTONES.md`, `docs/THREAT_MODEL.md` | edit | ADR-014, T3 mitigation now real, status. |

Reuses: `security/paths.py` (`expand_and_resolve`, `is_within`, `is_denied_path`), the
`ScopeEnforcer` gate + backstop, the R2 approval flow (unchanged).

## 4. `shell_policy.py`

```
EXECUTABLE_ALLOWLIST = { git, ls, cat, head, tail, wc, rg, grep, find, echo, pwd,
                         make, uv, python, python3, node, npm, pnpm, pytest }
SHELL_METACHARACTERS  = ; & | ` $ ( ) < > \n \r *  ?  (also reject leading ~ expansion, {})
```
- `parse_command(command, cwd)`:
  - reject empty; reject if the raw string contains any `SHELL_METACHARACTERS` → `ShellPolicyError`.
  - `argv = shlex.split(command)`; reject empty argv.
  - `path_tokens`: for each token in `argv[1:]`, if it looks like a path (contains `/`, starts with
    `~`, or is absolute), resolve it — absolute/`~` via `expand_and_resolve`, relative via
    `expand_and_resolve(Path(cwd) / token)` — and collect the resolved string.
  - returns `ParsedCommand(argv, path_tokens, exe=argv[0])`.
- `validate_executable(argv)`: `argv[0]` must be a **bare command name** (no `/`) that is in
  `EXECUTABLE_ALLOWLIST`, else `ShellPolicyError`. Rejecting `/` in the executable prevents running
  a malicious binary that merely shares an allowlisted basename (e.g. `/tmp/git`); the real binary
  is resolved from a controlled PATH (`/usr/bin:/bin:/usr/local/bin`), not an attacker-influenced
  one. (`sudo`, `rm`, `curl`, `ssh`, … are simply absent → refused.)

The allowlist is intentionally small and read/build-oriented. Adding an executable is a reviewed
change (it appears in this file + the ADR).

## 5. `shell_tool.py` — `ShellRun`

- **In** `{command: str, cwd: str}`; **Out** `{command, executed: bool, exit_code: int, stdout: str, stderr: str, truncated: bool}`.
- `default_risk = R2`; `supports_dry_run = True`; `timeout_s = 30.0`; `verification = OUTPUT_ASSERTION`;
  `redaction_fields = ["stdout", "stderr"]`.
- `requested_scope(args)`: **best-effort** — `try: p = parse_command(command, cwd)` and return
  `ResourceScope(paths=[cwd, *p.path_tokens])`; on `ShellPolicyError` (metachars/malformed) fall back
  to `ResourceScope(paths=[cwd])` and let `run()` reject the command. It must never raise, so the
  generic orchestrator scope-gate (which catches only `ScopeViolation`/`ValidationError`) stays
  decoupled from shell policy. For a clean command the enforcer checks the cwd **and every path-like
  arg**, so `cat /etc/passwd` / `cat ../x` / a denylisted path fail the gate **before** execution and
  before approval; a metachar command passes the cwd check, is shown for approval, and is refused in
  `run()` before any spawn (no shell ⇒ nothing smuggled runs either way).
- `run(args, dry_run)`:
  1. `p = parse_command(command, cwd)`; `validate_executable(p.argv)` (raise → refused, no spawn).
  2. resolve+verify `cwd` is a real directory (`expand_and_resolve`); else raise.
  3. **dry_run** → return `{executed: False, exit_code: 0, stdout: "[dry-run] " + shlex.join(argv), stderr: "", truncated: False}`; no process.
  4. else spawn `create_subprocess_exec(*argv, cwd=resolved_cwd, stdout=PIPE, stderr=PIPE)` with
     **no env inheritance of secrets** (pass a minimal env: PATH + HOME only).
  5. `await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s)`; on `TimeoutError`
     terminate→kill and raise. On `CancelledError` terminate→kill and re-raise (registry reports
     cancelled).
  6. cap `stdout`/`stderr` at 32 KiB each (truncate + set `truncated`); decode UTF-8 `errors="replace"`.
  7. non-zero `exit_code` → raise `RuntimeError("command exited N: <capped stderr>")` (→ `ok=False`,
     verification fails, recovery). exit 0 → return the typed output.

Because `requested_scope` returns all path tokens, the **primary gate + registry backstop** enforce
argument containment with no new policy code; `run()` adds the allowlist / metachar / non-shell /
cap / cancel mechanics.

## 6. Redaction & residual risk

`stdout`/`stderr` are `redaction_fields` → masked in the audit store, JSONL logs, and WS emit (one
boundary in `registry.execute`), so command output never persists (invariant 7). Consequence: the
live UI sees output masked this slice — live surfacing needs a separate non-persisted channel
(deferred), consistent with slice-3 fs content. **Residual risk (documented):** a secret embedded in
a command *argument* is recorded in the audit `command` field; mitigated because every R2 command is
explicitly shown and approved by the user before it runs.

## 7. Cancellation & timeout

`run()` owns the subprocess. On timeout or `asyncio.CancelledError`, it `proc.terminate()` then, if
still alive after a short grace, `proc.kill()` — no orphaned process. The registry's existing
timeout wrapper and the orchestrator's cancel race remain the outer mechanism.

## 8. Testing (TDD, incl. rejected paths + real OS)

- **`shell_policy.py`**: metachars (`;`, `&&`, backtick, `$()`, `>`, `*`) rejected; `shlex` parse;
  path tokens extracted for `/`-containing/absolute/`~` args, not for flags; off-list exec rejected;
  `sudo`/`rm` rejected.
- **`ShellRun.requested_scope`**: returns `[cwd]` for `git status`; `[cwd, /etc/passwd]` for
  `cat /etc/passwd`; propagates `ShellPolicyError` for `ls; rm -rf ~`.
- **`ShellRun.run` (real subprocess in tmp)**: `echo hi` → exit 0, stdout "hi"; dry_run runs nothing;
  non-zero exit (`python -c "import sys;sys.exit(3)"`) → failed result; off-list (`sudo …`) → refused;
  timeout (a sleep past 30 s is impractical — use a small injected timeout in a unit variant) →
  reported; output cap truncates.
- **Scope integration (real)**: through the registry with `allowed_scope = tmp`, `cat /etc/passwd`
  and a denylisted path are refused by the backstop; an in-scope `ls` runs.
- **Orchestrator R2 flow**: a plan step using `shell_run` → `WAITING_FOR_APPROVAL`; approve → runs;
  deny → FAILED, never executed (reuses the slice-2 approval tests' shape with a custom planner).
- **Regression**: full suite green; mocks untouched.

## 9. Live-OS verification

A scripted smoke test in a temp git repo: `git status`, `ls -la`, `cat <file>` run and return real
output; `sudo -v`, `rm -rf /tmp/x`, `cat /etc/passwd`, `ls ; echo hi` are each refused (allowlist /
broad-delete-not-allowlisted / scope / metachar). Only then does STATUS record a real, verified
restricted-shell capability.

## 10. ADR

**ADR-014:** restricted shell = allowlisted-exec + `shell=False` (no interpretation) + metachar
rejection + `requested_scope` returning every path token (so the slice-1 enforcer contains argument
paths) + R2 approval-per-command + output cap + `stdout/stderr` redaction + SIGTERM→SIGKILL cancel.
Rejected: a real shell with sanitization (unsafe); per-command risk classification (policy consumes
typed inputs, not parsed commands); allowlist-by-denylist (fails open). Env is minimized (PATH+HOME)
so subprocesses don't inherit secrets.
