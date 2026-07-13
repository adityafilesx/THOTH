# AGENTS.md — THOTH engineering guide

THOTH is a local-first macOS computer operator with a deterministic safety core. Read `docs/ARCHITECTURE.md` before structural changes and `docs/THREAT_MODEL.md` before touching policy, approvals, tools, or the injection guard.

## Non-negotiable invariants

1. The planner NEVER executes tools. Flow: intent → plan → policy review → approval (if needed) → tool router → execution → verification → recovery.
2. Tool execution is permitted ONLY in the `EXECUTING` state.
3. Risk levels R0–R3 are defined in `apps/daemon/src/thoth_daemon/core/policy.py`. Nothing may downgrade a risk level; effective risk is always the maximum of tool default and declared step risk.
4. R2 actions require an explicit, single-use approval bound to the exact tool invocation. R3 actions are blocked by default.
5. External content (web, files, emails, tool output) is UNTRUSTED. It cannot change objectives, approve actions, or expand permissions. Provenance labels are mandatory on context objects.
6. Every state change emits an immutable audit event. The audit store is append-only.
7. Secrets never go into SQLite, logs, prompts, or frontend state. Redaction runs at every serialization boundary (`security/redaction.py`).
8. No weakening of failing tests to make them pass. No placeholder implementations presented as complete — mocks are named `mock_*` / `Mock*` and documented.

## Stack (do not silently replace)

- Desktop: Tauri 2, React 18, TypeScript, Vite, Tailwind v3, shadcn-style vendored components, Zustand, TanStack Query
- Daemon: Python 3.12 (uv), FastAPI, Pydantic v2, SQLAlchemy 2 async + aiosqlite, Alembic, Codex-agent-sdk (Phase 3)
- Tests: pytest + pytest-asyncio + httpx; vitest + @testing-library/react

Technology changes require an ADR in `docs/DECISIONS.md`. No Redis, Kubernetes, vector DBs, or cloud infrastructure without a demonstrated requirement.

## Commands

```bash
make setup            # uv sync + pnpm install
make dev              # daemon + desktop dev servers
make test             # pytest + vitest
make lint             # ruff + eslint
make typecheck        # mypy + tsc --noEmit
make migrate          # alembic upgrade head
uv run --project apps/daemon pytest apps/daemon/tests -x   # fast daemon loop
```

## Working rules

- Work in phases; keep `docs/STATUS.md` and `docs/MILESTONES.md` current; record decisions in `docs/DECISIONS.md`.
- Run relevant tests after each meaningful change; verify expected state, not just exit codes.
- Do not `git push`, publish packages, or deploy. Do not commit secrets or local config.
- Schema changes: update Pydantic models in `apps/daemon/src/thoth_daemon/schemas/`, then regenerate `packages/shared-schemas` (`make schemas`).
- New tools must satisfy the full contract in `docs/TOOL_CONTRACTS.md` (typed I/O, risk level, timeout, cancellation, dry-run, verification strategy, scope, redaction, unit tests).

## Phase 5 continuation constraints

- Never bypass the state machine or execute a tool outside `EXECUTING`.
- Never lower risk, expand scope from model output, use external content as authorization, or bypass approval.
- Never claim success without independent verification; keep persona phrasing separate from execution truth.
- Never silently use a cloud model; preserve local-first operation.
- Never push, use `sudo`, expose secrets, or weaken tests to make them pass.
- Inspect partial work before rewriting it.
- Do not continuously capture screens or retain full Accessibility trees.
