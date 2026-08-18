---
name: thoth-dev
description: Development workflow for the THOTH repo — commands, invariants, phase-gate checklist. Use when implementing or reviewing any THOTH change.
---

# THOTH development workflow

## Before touching code

1. Read `AGENTS.md` (invariants + stack), then the doc matching your area:
   safety core → `docs/THREAT_MODEL.md`; tools → `docs/TOOL_CONTRACTS.md`;
   contracts → `docs/ARCHITECTURE.md` §5; tests → `docs/TEST_PLAN.md`.
2. Check `docs/STATUS.md` for what is real vs mocked. Do not build on a mock as if it were real.

## Command cheat-sheet

```bash
make setup                                             # install everything
uv run --project apps/daemon pytest apps/daemon/tests  # daemon tests
pnpm -C apps/desktop test -- --run                     # desktop tests
make lint typecheck                                    # ruff+mypy, eslint+tsc
make migrate                                           # alembic upgrade head
make schemas                                           # regenerate shared-schemas
make dev                                               # daemon :7710 + vite dev
```

## TDD loop (mandatory)

Failing test → minimal code → green → refactor → commit (Conventional Commits). Safety-core changes test both the allowed and rejected paths.

## Phase-gate checklist (before marking any phase complete)

- [ ] All suites green (`make test`) — quote summary lines
- [ ] `make lint typecheck` clean
- [ ] `make build` succeeds
- [ ] `docs/STATUS.md` + `docs/MILESTONES.md` updated truthfully
- [ ] Mocked capabilities listed explicitly; no capability overclaim
- [ ] Safety invariants re-verified (no execution outside EXECUTING, approvals enforced, no downgrade, redaction, append-only audit)
