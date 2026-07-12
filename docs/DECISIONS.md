# THOTH Decision Records

Format: lightweight ADRs. Newest last. A decision is binding until superseded by a later ADR.

## ADR-001: Python toolchain — uv with pinned CPython 3.12
**Date:** 2026-07-11 · **Status:** Accepted
Spec pins Python 3.12; the dev machine ships 3.14 and Homebrew pythons 3.9–3.11/3.14. `uv` installs and pins CPython 3.12.13 (`.python-version`), provides lockfiles and fast venvs. Alternative (brew python@3.12) rejected: no lockfile story, PATH fragility.

## ADR-002: ORM — SQLAlchemy 2.0 async, not SQLModel
**Date:** 2026-07-11 · **Status:** Accepted
Spec allows either. SQLModel couples API contracts to table models and historically lags Pydantic v2 releases. We keep Pydantic v2 contracts (`schemas/`) separate from SQLAlchemy table models (`storage/models.py`) — contracts are the API, tables are persistence. Driver: `aiosqlite`. Migrations: Alembic.

## ADR-003: JS toolchain — pnpm 10 via corepack
**Date:** 2026-07-11 · **Status:** Accepted
Spec requires a pnpm workspace. corepack pins pnpm per-repo (`packageManager` field) without a global install.

## ADR-004: Tailwind v3.4, shadcn components vendored by hand
**Date:** 2026-07-11 · **Status:** Accepted
shadcn/ui is copy-in by design. Hand-vendoring (cva + Radix primitives) avoids CLI codegen nondeterminism and network fetches during scaffold; Tailwind v3.4 because the vendored idiom targets it. Revisit v4 when shadcn's v4 templates stabilize (supersede via new ADR).

## ADR-005: claude-agent-sdk declared, planner mocked until Phase 3
**Date:** 2026-07-11 · **Status:** Accepted
Phase 2 requires deterministic tests and no real capability. `PlannerAdapter` interface is frozen now; `DeterministicMockPlanner` (keyword → fixed plan over mock tools) ships in Phase 2. The SDK integration is Phase 3 and must not change the adapter contract. The dependency is added at Phase 3 to keep the Phase 2 lockfile minimal.

## ADR-006: Event transport — in-process asyncio pub/sub
**Date:** 2026-07-11 · **Status:** Accepted
Single daemon process; an in-process `EventBus` fanned out to WebSocket clients suffices. Redis/message brokers explicitly rejected per spec ("no infrastructure without demonstrated requirement").

## ADR-007: IDs and audit ordering
**Date:** 2026-07-11 · **Status:** Accepted
Entity IDs: UUIDv4 strings. Audit ordering: per-task monotonic integer `seq` assigned by the audit store under a lock, so ordering tests are deterministic and independent of wall-clock resolution. Global order: (`created_at`, autoincrement rowid).

## ADR-008: Daemon port 7710, localhost-only
**Date:** 2026-07-11 · **Status:** Accepted
Fixed default port (7710 — "T" = 20th letter, TH=7,10 mnemonic) on `127.0.0.1`. No remote binding option in Phases 0–2. Desktop↔daemon auth token deferred to Phase 3 (residual risk recorded in THREAT_MODEL §5).

## ADR-009: Mock-tool naming and side-effect rules
**Date:** 2026-07-11 · **Status:** Accepted
All Phase 2 tools are prefixed `mock_`, operate on in-memory fixtures only, and are documented in TOOL_CONTRACTS §6. Presenting a mock as a real capability is a review-blocking defect.

## ADR-010: Audit tamper-evidence deferred
**Date:** 2026-07-11 · **Status:** Accepted
Audit store is append-only by API (no update/delete surface). Cryptographic hash-chaining considered and deferred to Phase 3 — no adversary in the Phase 0–2 threat surface can write to the DB without owning the process. Recorded as residual risk.

## ADR-011: Central ScopeEnforcer completes "executor enforces resource_scope"
**Date:** 2026-07-12 · **Status:** Accepted
`ToolDefinition.requested_scope(args)` declares the concrete paths/domains/apps an invocation will touch. A stateless `ScopeEnforcer` (`core/scope.py`) checks it against the effective allowed scope resolved by `PermissionStore` — first at the orchestrator pre-EXECUTING gate (fail fast: task FAILED, never enters EXECUTING, retry budget untouched), then again in `registry.execute` as a backstop. This implements the previously-unenforced "executor enforces resource_scope" clause of TOOL_CONTRACTS §1. Rejected: per-tool ad-hoc checks (un-auditable, forgettable) and executor-only enforcement (misses fail-fast before EXECUTING). Grants are mutated only through the trusted `/api/permissions` endpoints, so untrusted content can never widen scope. Path safety (`security/paths.py`) resolves symlinks and denies credential/system locations even inside an approved root.

## ADR-012: Per-session bearer token for desktop↔daemon
**Date:** 2026-07-12 · **Status:** Accepted
The daemon mints a `secrets.token_urlsafe(32)` session token at startup (or reads `THOTH_SESSION_TOKEN`), stores it on `app.state`, and writes it 0600 for the desktop to read. A pure-ASGI middleware requires `Authorization: Bearer <token>` (constant-time `secrets.compare_digest`) on every route except `/api/health`; the WebSocket requires a first-message `{type:"auth",token}` handshake (browsers can't set WS headers). Auth is **always on** — no disable flag to ship off. Implemented as a pure ASGI middleware rather than Starlette's `BaseHTTPMiddleware`, which does not pass WebSocket scopes through cleanly and hangs them. Rejected: query-param WS token (URL logging); a runtime bypass flag (ship-off risk); OS-keychain handoff (heavier than warranted for an ephemeral per-session token). Deliberate, scoped exception to "no secrets in frontend state": the token is IPC auth material, held in webview memory only, never persisted client-side, and redacted from logs/audit (`token`/`authorization` keys). The desktop reads it via the first custom Tauri command `session_token` (packaged) or `VITE_THOTH_TOKEN` (dev browser).

## ADR-013: Real filesystem tools added behind the scope contract
**Date:** 2026-07-12 · **Status:** Accepted
`fs_read_file`, `fs_list_dir`, `fs_write_file`, `fs_stat` are added (not replacing the mocks) as typed `ToolDefinition`s that declare `requested_scope(paths=[path])`, so the slice-1 `ScopeEnforcer` gate + registry backstop enforce them with **no new policy code** — verified against the real filesystem (out-of-scope, denylisted, and symlink-escape paths are all refused). Writes are atomic (temp file + `os.replace` in the same dir) and self-verified by read-back inside `run()`; `content` is a redaction field so file contents never persist to SQLite/logs/WS (and are masked in the live event stream in this slice — a content-surfacing UI needs a separate non-persisted channel, deferred). Deletion/move/copy deferred to the destructive-action review in later slices. End-to-end goal→plan→read awaits the claude-agent-sdk planner (slice 8); the capability is proven now via unit + orchestrator/backstop + live-OS tests.

## ADR-014: Restricted shell = allowlisted argv, no shell, scope-contained args
**Date:** 2026-07-12 · **Status:** Accepted
`shell_run` is the only tool taking a command string, but it never uses a shell: `shlex.split` + `create_subprocess_exec(shell=False)`, so `;&|`$()<>*?{}`/newline are neither interpreted nor accepted (rejected outright). Only bare-name executables in a small `EXECUTABLE_ALLOWLIST` run (no `/` in the exe → no `/tmp/git` spoofing; resolved via a controlled `PATH`); `sudo`/`rm`/`curl`/`ssh` are absent → refused. `requested_scope` returns `[cwd, *path_tokens]` — every path-like argument, resolved against cwd — so the slice-1 `ScopeEnforcer` contains argument escapes (`cat /etc/passwd`, `cat ../x`, denylisted paths) with **no new policy code**. Default risk **R2**: every command needs an explicit single-use approval bound to the exact argv. Output is capped (32 KiB/stream) and `stdout`/`stderr` are redaction fields (never persisted); subprocesses get a minimal env (PATH+HOME, no secret inheritance), `stdin=DEVNULL`, and SIGTERM→SIGKILL on timeout/cancel. Rejected: a real shell with sanitization (unsafe); per-command risk classification (policy consumes typed inputs, not parsed commands); allowlist-by-denylist (fails open). Residual, documented: a secret embedded in a command *argument* is recorded in the audit `command` field, mitigated by mandatory per-command approval. Regex metacharacters (`*`/`?`) in patterns are also rejected for now — a known usability limitation.

## ADR-015: Dedicated git tools over shell_run routing
**Date:** 2026-07-12 · **Status:** Accepted
`git_status`/`git_log`/`git_diff` (R0, structured output, no approval) and `git_add`/`git_commit` (R1) wrap git via `run_git` (`create_subprocess_exec`, controlled PATH, `stdin=DEVNULL`, `GIT_TERMINAL_PROMPT=0`, 64 KiB cap, timeout with terminate→kill). `requested_scope` puts the repo cwd — and for `git_add` every path argument, resolved against cwd — under the slice-1 `ScopeEnforcer` (no new policy code). `git_commit` self-verifies via `git rev-parse HEAD`; `git_diff.diff` is a redaction field (patches can contain secrets). Chosen over routing git through `shell_run`, which is R2-always (approval fatigue for reads), unstructured, and masked. `git push`/`pull`/`fetch` (network, R2) and history-mutating ops (`reset`/`rebase`/`checkout`) deferred — push additionally requires a real remote to verify against, unavailable this phase. Residual: a secret typed into a commit `message` is recorded in audit; user-authored, R1-gated.

## ADR-016: Desktop views wired to real daemon state (no seeds)
**Date:** 2026-07-12 · **Status:** Accepted
Permissions/Skills/Settings render live daemon state via TanStack Query over the auth'd client. New daemon endpoints: `GET/PATCH /api/skills` (over a `SkillStore` on the `skills` table; PATCH toggles `enabled` and audits `skill.toggled`) and read-only `GET /api/settings` (planner, approval TTL, retry budgets, trusted workspaces, version — never any secret/token). All sit under the slice-2 bearer middleware. **No seed data:** the Skills list is empty until the skill engine ships — an honest empty state, not fixtures dressed as real (which would violate the no-overclaim rule). The Settings "retention" placeholders (90d/14d) were removed because they were invented, not real config. Permissions Revoke really calls `DELETE`; the Skills toggle really PATCHes. Skill-engine execution, settings editing, and add-grant/add-workspace UI are deferred.
