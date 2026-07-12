# THOTH Status

**As of:** 2026-07-12 · **Phases 0, 1, 2 complete. All nine Phase 3 slices built (1–9)** — scope enforcement + permission store; session auth token; filesystem tools; restricted shell; git tools; macOS app launch/focus/list; scoped browser read; **real planner behind the frozen PlannerAdapter**; Permissions/Skills/Settings views wired. **Three live-verification gaps remain, each needing an environment this session lacked:** the planner's live Anthropic call (an API key), app control's AX *element* interaction (Accessibility TCC), and git `push` (a network remote).

## Where we are

- **Phase 0 — complete.** Plan, repo configuration, all engineering docs, and Claude Code agents/hooks/rules/skill. Hooks self-tested (17/17 block/allow cases).
- **Phase 1 — complete.** FastAPI daemon (health, WebSocket event stream, SQLite + Alembic, JSONL logging with redaction); Tauri 2 + React desktop shell with all seven views; typed API client + reconnecting WebSocket.
- **Phase 2 — complete.** Full safety core against **mock tools only**: 15 Pydantic contracts, deterministic state machine, risk/policy engine, injection guard, single-use approvals, tool registry, verification, bounded recovery, append-only audit store, orchestrator, task API + WebSocket events, frontend wired to the live flow.

## Verification (all green)

| Gate | Result |
|---|---|
| `uv run --project apps/daemon pytest` | **400 passed** |
| `ruff check apps/daemon` | All checks passed |
| `ruff format --check apps/daemon` | 98 files formatted |
| `mypy apps/daemon/src` (strict) | no issues, 57 files |
| `pnpm -C apps/desktop test` (vitest) | **51 passed** |
| `pnpm -C apps/desktop lint` (eslint) | clean |
| `pnpm -C apps/desktop typecheck` (tsc) | clean |
| `pnpm -C apps/desktop build` (vite) | built |
| `cargo check` (src-tauri) | Finished |
| `alembic upgrade head` | applies; 8 tables |

**Total: 451 automated tests passing.**

Also verified end-to-end against a live daemon: R0 task → `COMPLETED`; R3 plan → `FAILED` at policy; R2 task → `WAITING_FOR_APPROVAL` → approve → `COMPLETED`; approval reuse → HTTP 404 (single-use); cancel → `CANCELLED`; audit sequence monotonic; no secrets in JSONL logs.

## Honest capability statement

**THOTH cannot yet autonomously control the computer.** Phase 3 has added real, scoped **filesystem** tools (read/list/write/stat), a **restricted shell** (`shell_run`: allowlisted commands, no shell interpretation, R2 approval per command, argument paths scope-contained), **git workflow tools** (`git_status`/`log`/`diff` R0; `git_add`/`commit` R1, self-verified; push deferred), and **macOS app control** (`app_list` R0; `app_launch`/`app_focus` R1 via PyObjC `NSWorkspace`, scoped by `approved_apps`) — and a **scoped browser** (`browser_read` R1 via headless Chromium/Playwright, domain-allowlisted through `approved_domains`, web text `WEB_UNTRUSTED` + redacted) — all verified against the real OS (real app launch/focus non-intrusive; real navigation to `example.com`, off-list domains refused; AX element interaction deferred to a TCC follow-up). But there is still no voice — and the **real planner is implemented but its live Anthropic call is unverified here** (no API key). A `ClaudePlanner` behind the frozen `PlannerAdapter` makes a planning-only structured call to Claude and returns a plan over the real tools; its logic and untrusted-output containment are unit-tested, but nothing in this session drove a real goal→plan→execute end to end, so **no autonomous-control claim is made**. The default planner stays the offline mock. The safety core (state machine, policy, **scope enforcement**, approvals, **session auth**, audit) is real and tested and gates every tool. No broad control claim until the remaining adapters and the real planner land and are verified.

## Mocked / not yet implemented

- **Tools:** the nine `mock_*` tools remain (safety-core tests + mock planner). **Real, scoped filesystem tools** (`fs_read_file`/`fs_list_dir`/`fs_write_file`/`fs_stat`), a **restricted shell** (`shell_run` — allowlisted argv, R2 approval, scope-contained), **git tools** (`git_status`/`git_log`/`git_diff`/`git_add`/`git_commit`; push deferred), **macOS app tools** (`app_list`/`app_launch`/`app_focus` via NSWorkspace; AX element interaction deferred), and a **browser tool** (`browser_read` via Playwright, domain-allowlisted; clicking/forms deferred) now exist, all enforced by the scope gate + registry backstop.
- **Planner:** default is `DeterministicMockPlanner` (keyword → fixed plan). A real **`ClaudePlanner`** now exists behind the frozen `PlannerAdapter` (`THOTH_PLANNER=claude`) — a planning-only Anthropic Messages call (`claude-opus-4-8`, structured output) whose untrusted plan is validated by the same schema/registry/policy/scope gates and which **never executes tools** (ADR-019). Implemented + unit-tested; the live API call is **pending real-key verification**.
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

All nine Phase-3 slices are built. Remaining **live-verification** (each blocked on environment this session lacked, not on code): the planner's live Anthropic call (`ANTHROPIC_API_KEY` + `THOTH_PLANNER=claude`), app control's **AX element interaction** (Accessibility TCC), git `push` (a network remote). Then voice (out of this goal's scope). Each must be verified against the real OS before any control claim. See `docs/MILESTONES.md`.
