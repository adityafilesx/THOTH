# THOTH Milestones

## Phase 0 — Foundations (docs, repo, Claude Code config)

- [x] Implementation plan (`docs/superpowers/plans/2026-07-11-thoth-phase-0-2.md`)
- [x] Repo root: README, CLAUDE.md, CONTRIBUTING, SECURITY, .env.example, Makefile, pnpm-workspace, pyproject, CI
- [x] Engineering docs: PRD, ARCHITECTURE, THREAT_MODEL, TOOL_CONTRACTS, PRIVACY, TEST_PLAN, MILESTONES, DECISIONS, STATUS
- [x] `.claude/agents` — architect, backend-engineer, desktop-engineer, macos-automation-engineer, security-reviewer, qa-engineer, integration-reviewer (all `model: fable`; architect + security-reviewer read-only)
- [x] `.claude/hooks` — credential/`sudo`/`rm -rf`/`git push`/publish/deploy blocking; command logging; post-edit formatting; pre-completion test reminder
- [x] `.claude/rules` + `.claude/skills`

## Phase 1 — Shells and plumbing

- [ ] FastAPI daemon skeleton (`apps/daemon`): app factory, config, lifespan
- [ ] `GET /api/health` (+ db check)
- [ ] WebSocket event stream (`/ws`) + in-process EventBus
- [ ] SQLite via SQLAlchemy 2 async + Alembic migration 0001
- [ ] JSONL structured logging with redaction
- [ ] Tauri 2 + React + Vite + Tailwind desktop shell
- [ ] Desktop↔daemon connectivity (typed API client + reconnecting WS)
- [ ] Command-center UI (input, state chips, Stop)
- [ ] Plan + activity timeline UI on clearly-marked mock data
- [ ] Daemon tests: health, WS, logging/redaction
- [ ] Desktop tests: view rendering, badges

## Phase 2 — Safety core (mock tools only)

- [ ] Pydantic contracts (14 models + enums + provenance) + shared-schemas export
- [ ] Deterministic task state machine + audit-emitting transitions
- [ ] Risk & policy engine (R0–R3, no downgrade, unknown-tool denial)
- [ ] Prompt-injection guard (provenance firewall, directive flagging)
- [ ] Approval engine (single-use, invocation-bound, TTL)
- [ ] Tool registry + typed contracts + 9 mock tools
- [ ] Verification engine + VerificationResult routing
- [ ] Recovery controller (bounded retries; denials never retried)
- [ ] Append-only audit store + redaction at all boundaries
- [ ] Orchestrator + task API endpoints + WS task events
- [ ] Frontend wired to real task flow (create, approve, deny, cancel, timeline)
- [ ] Full test matrix green (see TEST_PLAN.md)

## Phase 3 — Real capability (NOT STARTED — deliberately)

- [ ] macOS adapters: app launch/focus (PyObjC/AX), typed AppleScript/JXA adapters
- [ ] Filesystem adapter with approved-directory scoping
- [ ] Restricted shell tool per TOOL_CONTRACTS §4
- [ ] Git workflow tools
- [ ] Browser adapter via Playwright MCP + domain allowlist
- [ ] claude-agent-sdk planner behind PlannerAdapter
- [ ] Desktop↔daemon session auth token
- [ ] Voice: push-to-talk capture, whisper.cpp/faster-whisper STT, `say` TTS
- [ ] Skill engine + Skills view wiring
- [ ] Permissions view wired to real grants/revocations

**THOTH cannot control the computer until Phase 3 lands and is verified.**
