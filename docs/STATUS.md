# THOTH Status

**As of:** 2026-07-11 · **Phases 0, 1, 2 complete.**

## Where we are

- **Phase 0 — complete.** Plan, repo configuration, all engineering docs, and Claude Code agents/hooks/rules/skill. Hooks self-tested (17/17 block/allow cases).
- **Phase 1 — complete.** FastAPI daemon (health, WebSocket event stream, SQLite + Alembic, JSONL logging with redaction); Tauri 2 + React desktop shell with all seven views; typed API client + reconnecting WebSocket.
- **Phase 2 — complete.** Full safety core against **mock tools only**: 15 Pydantic contracts, deterministic state machine, risk/policy engine, injection guard, single-use approvals, tool registry, verification, bounded recovery, append-only audit store, orchestrator, task API + WebSocket events, frontend wired to the live flow.

## Verification (all green)

| Gate | Result |
|---|---|
| `uv run --project apps/daemon pytest` | **256 passed** |
| `ruff check apps/daemon` | All checks passed |
| `ruff format --check apps/daemon` | 54 files formatted |
| `mypy apps/daemon/src` (strict) | no issues, 35 files |
| `pnpm -C apps/desktop test` (vitest) | **42 passed** |
| `pnpm -C apps/desktop lint` (eslint) | clean |
| `pnpm -C apps/desktop typecheck` (tsc) | clean |
| `pnpm -C apps/desktop build` (vite) | built |
| `cargo check` (src-tauri) | Finished |
| `alembic upgrade head` | applies; 6 tables |

**Total: 298 automated tests passing.**

Also verified end-to-end against a live daemon: R0 task → `COMPLETED`; R3 plan → `FAILED` at policy; R2 task → `WAITING_FOR_APPROVAL` → approve → `COMPLETED`; approval reuse → HTTP 404 (single-use); cancel → `CANCELLED`; audit sequence monotonic; no secrets in JSONL logs.

## Honest capability statement

**THOTH cannot control the computer.** There is no macOS automation, browser control, shell execution, or voice processing. Everything in Phase 2 runs against **mock tools** (`mock_*`, in-memory, no side effects). The safety core is real and tested; the capabilities it gates are not yet built. Real integration is Phase 3 and must be verified before any control claim is made.

## Mocked / not yet implemented

- **Tools:** all nine tools are mocks (`apps/daemon/src/thoth_daemon/tools/mock_tools.py`). No real filesystem, app, browser, git, or shell action occurs.
- **Planner:** `DeterministicMockPlanner` (keyword → fixed plan). The claude-agent-sdk planner is deferred to Phase 3 behind the frozen `PlannerAdapter` interface.
- **Voice:** none. Push-to-talk, STT, and TTS are Phase 3.
- **Desktop views:** Permissions, Skills, and Settings render static fixtures (labeled "mock data"); they are not yet wired to daemon state.
- **Security:** no desktop↔daemon auth token yet (localhost-only); audit store is append-only by API but not cryptographically tamper-evident. Both recorded as residual risks in `docs/THREAT_MODEL.md`.

## How to run

```bash
make setup                       # install daemon + desktop deps
make migrate                     # create the SQLite schema
make dev                         # daemon on :7710 + Vite dev server
# native shell instead of browser:  cd apps/desktop && pnpm tauri dev
```

## Next

Phase 3: real macOS/browser/shell/filesystem adapters behind the existing tool contracts, the claude-agent-sdk planner, voice, and the desktop↔daemon auth token. See `docs/MILESTONES.md`.
