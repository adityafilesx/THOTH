# THOTH Milestones

## Phase 0 — Foundations (docs, repo, Claude Code config)

- [x] Implementation plan (`docs/superpowers/plans/2026-07-11-thoth-phase-0-2.md`)
- [x] Repo root: README, CLAUDE.md, CONTRIBUTING, SECURITY, .env.example, Makefile, pnpm-workspace, pyproject, CI
- [x] Engineering docs: PRD, ARCHITECTURE, THREAT_MODEL, TOOL_CONTRACTS, PRIVACY, TEST_PLAN, MILESTONES, DECISIONS, STATUS
- [x] `.claude/agents` — architect, backend-engineer, desktop-engineer, macos-automation-engineer, security-reviewer, qa-engineer, integration-reviewer (all `model: fable`; architect + security-reviewer read-only)
- [x] `.claude/hooks` — credential/`sudo`/`rm -rf`/`git push`/publish/deploy blocking; command logging; post-edit formatting; pre-completion test reminder
- [x] `.claude/rules` + `.claude/skills`

## Phase 1 — Shells and plumbing

- [x] FastAPI daemon skeleton (`apps/daemon`): app factory, config, lifespan
- [x] `GET /api/health` (+ db check)
- [x] WebSocket event stream (`/ws`) + in-process EventBus
- [x] SQLite via SQLAlchemy 2 async + Alembic migration 0001
- [x] JSONL structured logging with redaction
- [x] Tauri 2 + React + Vite + Tailwind desktop shell
- [x] Desktop↔daemon connectivity (typed API client + reconnecting WS)
- [x] Command-center UI (input, state chips, Stop)
- [x] Plan + activity timeline UI on clearly-marked mock data
- [x] Daemon tests: health, WS, logging/redaction
- [x] Desktop tests: view rendering, badges

## Phase 2 — Safety core (mock tools only)

- [x] Pydantic contracts (14 models + enums + provenance) + shared-schemas export
- [x] Deterministic task state machine + audit-emitting transitions
- [x] Risk & policy engine (R0–R3, no downgrade, unknown-tool denial)
- [x] Prompt-injection guard (provenance firewall, directive flagging)
- [x] Approval engine (single-use, invocation-bound, TTL)
- [x] Tool registry + typed contracts + 9 mock tools
- [x] Verification engine + VerificationResult routing
- [x] Recovery controller (bounded retries; denials never retried)
- [x] Append-only audit store + redaction at all boundaries
- [x] Orchestrator + task API endpoints + WS task events
- [x] Frontend wired to real task flow (create, approve, deny, cancel, timeline)
- [x] Full test matrix green (see TEST_PLAN.md)

## Phase 3 — Real capability (IN PROGRESS)

- [x] **Slice 1 — Scope enforcement + permission store:** path-safety primitives (symlink-safe resolution + credential/system denylist), central `ScopeEnforcer` (orchestrator pre-EXECUTING gate + registry backstop), persistent `WorkspaceProfile`/`PermissionGrant` store, `/api/permissions` API. No real I/O yet.
- [x] **Slice 2 — Session auth token:** per-session bearer token, pure-ASGI HTTP middleware + WebSocket handshake (health exempt, constant-time compare), desktop attaches it via a Tauri command / dev env. Always-on. Closes threat T6.
- [x] **Slice 3 — Filesystem adapter (first real capability):** real scoped `fs_read_file`/`fs_list_dir`/`fs_write_file`/`fs_stat` — atomic self-verified writes, content redacted, gated by the slice-1 scope enforcer; verified against the real filesystem. Deletion/move deferred.
- [x] **Slice 4 — Restricted shell:** `shell_run` — allowlisted bare-name executables, no shell interpretation (metacharacters rejected), `requested_scope` contains cwd + every argument path, R2 approval per command, 32 KiB output cap, minimal env, SIGTERM→SIGKILL cancel; live-OS verified. The only command-string tool.
- [x] **Slice 5 — Git workflow tools:** `git_status`/`git_log`/`git_diff` (R0, structured) + `git_add`/`git_commit` (R1, self-verified via rev-parse), scoped repo cwd + add path args; `diff` redacted; live-OS verified in a real repo. Push/history ops deferred.
- [x] **Slice 6 — macOS app control:** `app_list` (R0), `app_launch`/`app_focus` (R1) via PyObjC `NSWorkspace`, scoped by `approved_apps`, state-probe self-verified; live-OS verified (real launch/focus, non-intrusive). AX *element* interaction (Accessibility TCC) deferred.
- [~] macOS adapters: app launch/focus (PyObjC) done; AX element interaction + AppleScript/JXA deferred (need TCC)
- [x] Filesystem adapter with approved-directory scoping
- [x] Restricted shell tool per TOOL_CONTRACTS §4
- [x] Git workflow tools (local ops; push deferred)
- [x] **Slice 7 — Browser adapter:** `browser_read` (R1) via headless Chromium/Playwright behind a swappable `BrowserAdapter`; domain allowlist enforced by the slice-1 scope enforcer (`requested_scope(domains=[host])`); web text `WEB_UNTRUSTED` + redacted; live-OS verified (real `example.com`, off-list refused). Playwright-Python in-daemon (MCP-swappable, see ADR-018); clicking/forms deferred.
- [ ] claude-agent-sdk planner behind PlannerAdapter
- [x] Desktop↔daemon session auth token
- [x] **Slice 9 — Views wired to real daemon state:** Permissions (live grants + revoke), Skills (live list + enable toggle; no seeds — empty until the engine ships), Settings (read-only real config) over `GET/PATCH /api/skills` + `GET /api/settings`.
- [ ] Voice: push-to-talk capture, whisper.cpp/faster-whisper STT, `say` TTS
- [~] Skill engine + Skills view wiring — **Skills view wired**; skill *engine* (execution) deferred
- [x] Permissions view wired to real grants/revocations

**THOTH cannot control the computer until Phase 3 lands and is verified.**
