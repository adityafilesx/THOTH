# THOTH Status

**As of:** 2026-07-12 · **Phases 0, 1, 2 complete. Phase 3 in progress — slices 1–6 + 9 landed** (scope enforcement + permission store; session auth token; filesystem tools; restricted shell; git tools; **macOS app launch/focus/list**; Permissions/Skills/Settings views wired). **Slices 7–8 (browser, planner) still deferred** — they need a Playwright MCP server / an Anthropic API key to verify against; and app control's AX *element* interaction needs Accessibility TCC grants.

## Where we are

- **Phase 0 — complete.** Plan, repo configuration, all engineering docs, and Claude Code agents/hooks/rules/skill. Hooks self-tested (17/17 block/allow cases).
- **Phase 1 — complete.** FastAPI daemon (health, WebSocket event stream, SQLite + Alembic, JSONL logging with redaction); Tauri 2 + React desktop shell with all seven views; typed API client + reconnecting WebSocket.
- **Phase 2 — complete.** Full safety core against **mock tools only**: 15 Pydantic contracts, deterministic state machine, risk/policy engine, injection guard, single-use approvals, tool registry, verification, bounded recovery, append-only audit store, orchestrator, task API + WebSocket events, frontend wired to the live flow.

## Verification (all green)

| Gate | Result |
|---|---|
| `uv run --project apps/daemon pytest` | **386 passed** |
| `ruff check apps/daemon` | All checks passed |
| `ruff format --check apps/daemon` | 89 files formatted |
| `mypy apps/daemon/src` (strict) | no issues, 53 files |
| `pnpm -C apps/desktop test` (vitest) | **51 passed** |
| `pnpm -C apps/desktop lint` (eslint) | clean |
| `pnpm -C apps/desktop typecheck` (tsc) | clean |
| `pnpm -C apps/desktop build` (vite) | built |
| `cargo check` (src-tauri) | Finished |
| `alembic upgrade head` | applies; 8 tables |

**Total: 437 automated tests passing.**

Also verified end-to-end against a live daemon: R0 task → `COMPLETED`; R3 plan → `FAILED` at policy; R2 task → `WAITING_FOR_APPROVAL` → approve → `COMPLETED`; approval reuse → HTTP 404 (single-use); cancel → `CANCELLED`; audit sequence monotonic; no secrets in JSONL logs.

## Honest capability statement

**THOTH cannot yet autonomously control the computer.** Phase 3 has added real, scoped **filesystem** tools (read/list/write/stat), a **restricted shell** (`shell_run`: allowlisted commands, no shell interpretation, R2 approval per command, argument paths scope-contained), **git workflow tools** (`git_status`/`log`/`diff` R0; `git_add`/`commit` R1, self-verified; push deferred), and **macOS app control** (`app_list` R0; `app_launch`/`app_focus` R1 via PyObjC `NSWorkspace`, scoped by `approved_apps`) — all verified against the real OS (real app launch/focus exercised non-intrusively; AX element interaction deferred to a TCC-gated follow-up). But there is still no browser control or voice — and, crucially, **no real planner** wiring a natural-language goal to these tools end to end (the deterministic mock planner drives only mock tools; the claude-agent-sdk planner is slice 8). The safety core (state machine, policy, **scope enforcement**, approvals, **session auth**, audit) is real and tested and gates every tool. No broad control claim until the remaining adapters and the real planner land and are verified.

## Mocked / not yet implemented

- **Tools:** the nine `mock_*` tools remain (safety-core tests + mock planner). **Real, scoped filesystem tools** (`fs_read_file`/`fs_list_dir`/`fs_write_file`/`fs_stat`), a **restricted shell** (`shell_run` — allowlisted argv, R2 approval, scope-contained), **git tools** (`git_status`/`git_log`/`git_diff`/`git_add`/`git_commit`; push deferred), and **macOS app tools** (`app_list`/`app_launch`/`app_focus` via NSWorkspace; AX element interaction deferred) now exist, all enforced by the scope gate + registry backstop. No browser tooling yet.
- **Planner:** `DeterministicMockPlanner` (keyword → fixed plan). The claude-agent-sdk planner is deferred to Phase 3 behind the frozen `PlannerAdapter` interface.
- **Voice:** none. Push-to-talk, STT, and TTS are Phase 3.
- **Desktop views:** Permissions, Skills, and Settings are now **wired to real daemon state** (TanStack Query over `/api/permissions`, `/api/skills`, `/api/settings`; live revoke + skill-toggle mutations). The Skills list is intentionally **empty** — no skill engine yet, so no fixtures. Command/Plan/Timeline already ran on the live task flow.
- **Security:** tool `resource_scope` is now **enforced** — a central `ScopeEnforcer` gates every step pre-EXECUTING and re-checks in the executor, backed by a persistent permission store + `/api/permissions` (slice 1). The daemon now **requires a per-session bearer token** on every endpoint except `/api/health`, plus a WebSocket auth handshake; the desktop attaches it (Tauri command / dev env), always-on (slice 2). Still pending: audit store is append-only by API but not cryptographically tamper-evident (residual risk in `docs/THREAT_MODEL.md`).

## How to run

```bash
make setup                       # install daemon + desktop deps
make migrate                     # create the SQLite schema
make dev                         # daemon on :7710 + Vite dev server
# native shell instead of browser:  cd apps/desktop && pnpm tauri dev
```

## Next

Remaining Phase 3 (deferred — need a Playwright MCP server / an Anthropic API key to verify): app control's **AX element interaction** (Accessibility TCC), **slice 7** browser (Playwright MCP + domain allowlist), **slice 8** claude-agent-sdk planner behind the frozen `PlannerAdapter`. Then voice. Each must be verified against the real OS before any control claim. See `docs/MILESTONES.md`.
