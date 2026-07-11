# THOTH Status

**As of:** 2026-07-12 · **Phases 0, 1, 2 complete. Phase 3 in progress — slices 1–4 (scope enforcement + permission store; session auth token; real scoped filesystem tools; restricted shell) landed.**

## Where we are

- **Phase 0 — complete.** Plan, repo configuration, all engineering docs, and Claude Code agents/hooks/rules/skill. Hooks self-tested (17/17 block/allow cases).
- **Phase 1 — complete.** FastAPI daemon (health, WebSocket event stream, SQLite + Alembic, JSONL logging with redaction); Tauri 2 + React desktop shell with all seven views; typed API client + reconnecting WebSocket.
- **Phase 2 — complete.** Full safety core against **mock tools only**: 15 Pydantic contracts, deterministic state machine, risk/policy engine, injection guard, single-use approvals, tool registry, verification, bounded recovery, append-only audit store, orchestrator, task API + WebSocket events, frontend wired to the live flow.

## Verification (all green)

| Gate | Result |
|---|---|
| `uv run --project apps/daemon pytest` | **353 passed** |
| `ruff check apps/daemon` | All checks passed |
| `ruff format --check apps/daemon` | 54 files formatted |
| `mypy apps/daemon/src` (strict) | no issues, 45 files |
| `pnpm -C apps/desktop test` (vitest) | **46 passed** |
| `pnpm -C apps/desktop lint` (eslint) | clean |
| `pnpm -C apps/desktop typecheck` (tsc) | clean |
| `pnpm -C apps/desktop build` (vite) | built |
| `cargo check` (src-tauri) | Finished |
| `alembic upgrade head` | applies; 8 tables |

**Total: 399 automated tests passing.**

Also verified end-to-end against a live daemon: R0 task → `COMPLETED`; R3 plan → `FAILED` at policy; R2 task → `WAITING_FOR_APPROVAL` → approve → `COMPLETED`; approval reuse → HTTP 404 (single-use); cancel → `CANCELLED`; audit sequence monotonic; no secrets in JSONL logs.

## Honest capability statement

**THOTH cannot yet autonomously control the computer.** Phase 3 has added real, scoped **filesystem** tools (read/list/write/stat) and a **restricted shell** (`shell_run`: allowlisted commands, no shell interpretation, R2 approval per command, argument paths scope-contained) — both verified against the real OS. But there is still no macOS app automation, browser control, or voice — and, crucially, **no real planner** wiring a natural-language goal to these tools end to end (the deterministic mock planner drives only mock tools; the claude-agent-sdk planner is slice 8). The safety core (state machine, policy, **scope enforcement**, approvals, **session auth**, audit) is real and tested and gates every tool. No broad control claim until the remaining adapters and the real planner land and are verified.

## Mocked / not yet implemented

- **Tools:** the nine `mock_*` tools remain (safety-core tests + mock planner). **Real, scoped filesystem tools** (`fs_read_file`/`fs_list_dir`/`fs_write_file`/`fs_stat`) and a **restricted shell** (`shell_run` — allowlisted argv, R2 approval, scope-contained) now exist, all enforced by the scope gate + registry backstop. No real app, browser, or git-specific tooling yet.
- **Planner:** `DeterministicMockPlanner` (keyword → fixed plan). The claude-agent-sdk planner is deferred to Phase 3 behind the frozen `PlannerAdapter` interface.
- **Voice:** none. Push-to-talk, STT, and TTS are Phase 3.
- **Desktop views:** Permissions, Skills, and Settings still render static fixtures (labeled "mock data"); wiring to daemon state is slice 9. The daemon-side permissions API + store are now real (see Security).
- **Security:** tool `resource_scope` is now **enforced** — a central `ScopeEnforcer` gates every step pre-EXECUTING and re-checks in the executor, backed by a persistent permission store + `/api/permissions` (slice 1). The daemon now **requires a per-session bearer token** on every endpoint except `/api/health`, plus a WebSocket auth handshake; the desktop attaches it (Tauri command / dev env), always-on (slice 2). Still pending: audit store is append-only by API but not cryptographically tamper-evident (residual risk in `docs/THREAT_MODEL.md`).

## How to run

```bash
make setup                       # install daemon + desktop deps
make migrate                     # create the SQLite schema
make dev                         # daemon on :7710 + Vite dev server
# native shell instead of browser:  cd apps/desktop && pnpm tauri dev
```

## Next

Phase 3: real macOS/browser/shell/filesystem adapters behind the existing tool contracts, the claude-agent-sdk planner, voice, and the desktop↔daemon auth token. See `docs/MILESTONES.md`.
