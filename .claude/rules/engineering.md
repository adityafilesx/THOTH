# Engineering rules (binding for all agents)

1. Work in phases; before coding, inspect the repo and write/update a concrete plan. Keep `docs/STATUS.md`, `docs/MILESTONES.md`, and `docs/DECISIONS.md` current.
2. TDD: failing test → minimal implementation → green. Safety-core changes require tests for the allowed AND the rejected path. Run tests after each meaningful change.
3. Never report success because a command exited 0 — verify the expected state and quote real output.
4. Never weaken a failing test to make it pass.
5. Mocks are named `mock_*` / `Mock*`, clearly documented, and never presented as completed features.
6. Do not silently replace chosen technologies (see CLAUDE.md stack). Any change needs an ADR.
7. No Redis, Kubernetes, vector databases, or cloud infrastructure without a demonstrated requirement and an ADR.
8. Keep modules small and typed: Pydantic v2 with `extra="forbid"` on external payloads; mypy strict; `tsc --noEmit` clean; no `any` without inline justification.
9. Conventional Commits; commit at task boundaries; never commit secrets, `.env`, databases, or logs.
10. Schema changes: update `apps/daemon/src/thoth_daemon/schemas/`, regenerate `packages/shared-schemas` (`make schemas`), and keep the desktop types in lockstep.
