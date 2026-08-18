# Contributing to OmniMac

## Setup

```bash
corepack enable pnpm
curl -LsSf https://astral.sh/uv/install.sh | sh   # if uv is missing
make setup
```

## Workflow

1. Branch from `main`. Never commit directly to `main` for non-trivial work.
2. Write the failing test first (TDD). Safety-core changes (state machine, policy, approvals, tools, audit, redaction) require tests for both the allowed and the rejected path.
3. Keep modules small and typed. One responsibility per file.
4. Run before every commit:
   ```bash
   make lint typecheck test
   ```
5. Update docs when behavior changes: `docs/STATUS.md`, `docs/MILESTONES.md`, and an ADR in `docs/DECISIONS.md` for any technology or contract change.

## Hard rules

- Do not push to remote repositories or publish packages from this repo's tooling.
- Do not commit secrets, `.env` files, databases, or logs.
- Do not weaken a failing test to make it pass.
- Do not present mocks as completed features; mocks are named `mock_*` / `Mock*`.
- No new infrastructure (Redis, Kubernetes, vector DB, cloud services) without an approved ADR.
- Risk levels and approval requirements may only be strengthened, never bypassed, in tests or code.

## Commit style

Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`). Subject ≤ 72 chars, body explains *why* when non-obvious.

## Code style

- Python: ruff (format + lint), mypy strict on `omnimac_daemon`. Async-first; no blocking I/O in the event loop.
- TypeScript: eslint + prettier defaults, `tsc --noEmit` clean. No `any` unless justified inline.
- Pydantic models use `extra="forbid"` for all externally-supplied payloads.
