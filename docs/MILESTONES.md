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
- [ ] macOS adapters: app launch/focus (PyObjC/AX), typed AppleScript/JXA adapters
- [ ] Filesystem adapter with approved-directory scoping
- [ ] Restricted shell tool per TOOL_CONTRACTS §4
- [ ] Git workflow tools
- [ ] Browser adapter via Playwright MCP + domain allowlist
- [ ] claude-agent-sdk planner behind PlannerAdapter
- [x] Desktop↔daemon session auth token
- [ ] Voice: push-to-talk capture, whisper.cpp/faster-whisper STT, `say` TTS
- [ ] Skill engine + Skills view wiring
- [ ] Permissions view wired to real grants/revocations

**THOTH cannot control the computer until Phase 3 lands and is verified.**
