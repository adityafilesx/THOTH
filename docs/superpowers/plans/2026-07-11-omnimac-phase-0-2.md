# OmniMac Phase 0–2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Granularity note:** This plan is executed inline by the authoring session immediately after writing. It specifies exact files, interfaces, contracts, and test matrices, but does not inline full source for every step. Key contracts (state transitions, risk table, tool contract) are given verbatim; module bodies are specified by responsibility + signature.

**Goal:** Deliver OmniMac Phase 0 (engineering docs + repo + Claude Code config), Phase 1 (Tauri/React shell + FastAPI daemon + WS + SQLite + logging + mocked UI), and Phase 2 (contracts, state machine, risk policy, approvals, tool registry with mocks, verification, recovery, audit, task API/WS) with tests.

**Architecture:** Monorepo. Python daemon (`apps/daemon`) owns all agent logic behind typed Pydantic contracts; a deterministic task state machine gates every tool execution; policy/approval engines run independently of model output. Desktop (`apps/desktop`) is a thin Tauri 2 + React client speaking HTTP + WebSocket to the daemon. No real macOS/browser/voice control in this scope — interfaces and mocks only.

**Tech Stack:** Tauri 2, React 18, TypeScript, Vite, Tailwind CSS v3, shadcn-style components (hand-vendored), Zustand, TanStack Query, Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async + aiosqlite, Alembic, pytest + pytest-asyncio + httpx, vitest + @testing-library/react.

## Global Constraints

- Python 3.12 (uv-managed, pinned `.python-version`).
- No Redis, Kubernetes, vector DB, or cloud infra.
- Planner never executes tools; tool execution only in `EXECUTING` state.
- No secrets in SQLite, logs, prompts, or frontend state.
- Risk levels R0–R3 exactly as specified; R3 blocked by default; no self-downgrade.
- Provenance labels: USER_TRUSTED, SYSTEM_TRUSTED, TOOL_RESULT_UNTRUSTED, WEB_UNTRUSTED, FILE_UNTRUSTED.
- All Claude agents `model: fable`; architect + security-reviewer read-only; no `bypassPermissions`.
- Mocks marked clearly; no placeholder presented as complete.
- No `git push`; no publishing; commits at task boundaries.

## Dependency Decision Record (mirrored into docs/DECISIONS.md)

| Decision | Choice | Rationale |
|---|---|---|
| Python toolchain | `uv` + pinned CPython 3.12.13 | Spec pins 3.12; system python is 3.14; uv gives lockfile + fast venv |
| ORM | SQLAlchemy 2.0 (async, aiosqlite) + separate Pydantic v2 contracts | Spec allows SQLAlchemy or SQLModel; SQLModel couples API contracts to table models and lags Pydantic releases |
| JS package manager | pnpm 10 via corepack | Spec requires pnpm workspace |
| Tailwind | v3.4 | shadcn idiom stable on v3; v4 CSS-first migration adds risk without benefit here |
| shadcn/ui | Hand-vendored components (cva + Radix primitives) | shadcn is copy-in by design; avoids CLI codegen nondeterminism |
| claude-agent-sdk | Declared dependency + `PlannerAdapter` interface; real calls deferred to Phase 3 | Phase 2 planner must be deterministic/mock per scope |
| PyObjC / Playwright MCP / whisper | NOT installed; interface stubs only | Phase 3+ scope; spec forbids real control now |
| Event transport | In-process async pub/sub fanned out to WebSocket | No broker allowed; single daemon process |
| IDs | UUIDv4 strings, `sortable created_at` + monotonic per-task sequence for audit ordering | Audit ordering test requires deterministic order |

## File Structure

```
OmniMac/
├── README.md  CLAUDE.md  CONTRIBUTING.md  SECURITY.md  .env.example  Makefile
├── pnpm-workspace.yaml  pyproject.toml  .python-version  .gitignore
├── .github/workflows/ci.yml
├── docs/{PRD,ARCHITECTURE,THREAT_MODEL,TOOL_CONTRACTS,PRIVACY,TEST_PLAN,MILESTONES,DECISIONS,STATUS}.md
├── .claude/
│   ├── settings.json                     # hooks wiring, permission deny rules
│   ├── agents/{architect,backend-engineer,desktop-engineer,macos-automation-engineer,security-reviewer,qa-engineer,integration-reviewer}.md
│   ├── hooks/{block_dangerous.py,log_commands.py,format_after_edit.py,test_before_complete.py}
│   ├── rules/{safety.md,engineering.md}
│   └── skills/omnimac-dev/SKILL.md
├── packages/
│   ├── shared-schemas/{package.json,schemas/*.json,src/index.ts}   # JSON Schema exported from Pydantic + TS types
│   └── design-tokens/{package.json,tokens.json,src/index.ts}
├── apps/daemon/
│   ├── pyproject.toml  alembic.ini  alembic/{env.py,versions/}
│   ├── src/omnimac_daemon/
│   │   ├── main.py app.py config.py logging_setup.py
│   │   ├── api/{health.py,tasks.py,approvals.py,ws.py}
│   │   ├── events/bus.py
│   │   ├── schemas/{enums.py,task.py,plan.py,tool.py,approval.py,audit.py,policy.py,verification.py,recovery.py,skill.py,workspace.py,provenance.py}
│   │   ├── core/{state_machine.py,policy.py,approvals.py,injection_guard.py,verification.py,recovery.py,orchestrator.py,planner.py}
│   │   ├── tools/{base.py,registry.py,mock_tools.py}
│   │   ├── storage/{db.py,models.py,repositories.py}
│   │   ├── audit/store.py
│   │   └── security/redaction.py
│   └── tests/  (mirrors src layout)
└── apps/desktop/
    ├── package.json vite.config.ts tsconfig.json tailwind.config.ts postcss.config.js index.html
    ├── src-tauri/{Cargo.toml,tauri.conf.json,build.rs,src/{main.rs,lib.rs},capabilities/default.json,icons/}
    └── src/
        ├── main.tsx App.tsx index.css
        ├── lib/{api.ts,ws.ts,utils.ts,types.ts}
        ├── stores/{connection.ts,tasks.ts,ui.ts}
        ├── components/ui/{button,card,badge,dialog,drawer,input,scroll-area,switch,tabs,tooltip}.tsx
        ├── components/{RiskBadge.tsx,StateBadge.tsx,StopButton.tsx,Layout.tsx}
        └── views/{CommandCenter,PlanView,ApprovalDrawer,Timeline,Permissions,Skills,Settings}.tsx
```

## Core Contracts (verbatim)

### State machine transitions

```python
TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    RECEIVED:             {UNDERSTANDING, CANCELLED, FAILED},
    UNDERSTANDING:        {PLANNING, CANCELLED, FAILED},
    PLANNING:             {RISK_REVIEW, CANCELLED, FAILED},
    RISK_REVIEW:          {WAITING_FOR_APPROVAL, EXECUTING, CANCELLED, FAILED},
    WAITING_FOR_APPROVAL: {EXECUTING, CANCELLED, FAILED},
    EXECUTING:            {VERIFYING, RECOVERING, WAITING_FOR_APPROVAL, CANCELLED, FAILED},
    VERIFYING:            {EXECUTING, COMPLETED, RECOVERING, CANCELLED, FAILED},
    RECOVERING:           {EXECUTING, FAILED, CANCELLED},
    COMPLETED:            set(),   # terminal
    FAILED:               set(),   # terminal
    CANCELLED:            set(),   # terminal
}
```
Every `transition()` emits an immutable `AuditEvent` before returning. Invalid transition → `InvalidTransitionError` (no state change, audit event `transition_rejected`).

- EXECUTING→WAITING_FOR_APPROVAL covers multi-step plans where a later step needs approval.
- VERIFYING→EXECUTING covers advancing to the next plan step.

### Risk policy

`PolicyDecision = {allowed: bool, requires_approval: bool, effective_risk: RiskLevel, reasons: list[str]}`.
Rules, in order: (1) unknown tool → deny; (2) effective_risk = max(tool default risk, plan-step declared risk) — never min (no downgrade); (3) R3 → deny (blocked_by_default); (4) R2 → requires_approval; (5) R1 → requires_approval unless `workspace.trusted`; (6) R0 → allowed if targets within approved scopes. Policy engine takes only typed inputs; never model text.

### Tool contract

`ToolDefinition{name, description, input_model, output_model, default_risk, timeout_s, supports_dry_run, supports_cancellation, verification: VerificationStrategy, resource_scope: ResourceScope, redaction_fields: list[str]}`. Registry rejects duplicate names; invocation validates args via `input_model` with `extra="forbid"`; unknown tool name → `UnknownToolError`.

### Approval enforcement

Executor requires, for every R2+ invocation, an `ApprovalDecision{approved=True, request_id, scope="once"}` recorded for exactly that `ToolInvocation.id`, granted while task in WAITING_FOR_APPROVAL, unexpired. Missing/denied/mismatched → `ApprovalRequiredError`; attempt audited as `execution_blocked`.

### Recovery

`RecoveryController(max_retries_per_step=2, max_retries_per_task=5)`. Retry only tool timeouts/transient failures and failed verifications; never retry policy denials or approval denials. Exhaustion → FAILED with audit trail.

### Redaction

`redact(obj) -> obj` masks values whose keys match `{password, secret, token, api_key, authorization, credential, cookie}` (case-insensitive, nested) to `"[REDACTED]"` plus tool-declared `redaction_fields`. Applied at: audit store write, JSONL log write, WS event serialization.

---

## Tasks

### Task 0.1: Repo root + config
Files: `.gitignore`, `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`, `.env.example`, `Makefile`, `pnpm-workspace.yaml`, `pyproject.toml` (uv workspace, ruff+mypy config), `.python-version`, `.github/workflows/ci.yml`.
- [ ] Write all files. Makefile targets: `setup, daemon, desktop, dev, test, test-daemon, test-desktop, lint, typecheck, build, migrate`.
- [ ] CI: two jobs (daemon: uv sync→ruff→mypy→pytest; desktop: pnpm install→eslint→tsc→vitest→vite build). No deploy steps.
- [ ] Commit.

### Task 0.2: Engineering docs
Files: `docs/{PRD,ARCHITECTURE,THREAT_MODEL,TOOL_CONTRACTS,PRIVACY,TEST_PLAN,MILESTONES,DECISIONS,STATUS}.md`.
- [ ] Each doc substantive: PRD (goals/non-goals/workflows/UX views), ARCHITECTURE (module map, flow diagram, event model), THREAT_MODEL (assets, adversaries incl. prompt injection, mitigations mapped to modules), TOOL_CONTRACTS (contract fields + shell tool restrictions), PRIVACY (local-first, retention, Keychain), TEST_PLAN (test matrix from spec), MILESTONES (phase checklists, 0–2 detailed), DECISIONS (ADR list from table above), STATUS (current truth).
- [ ] Commit.

### Task 0.3: Claude Code config
Files: `.claude/settings.json`, 7 agent files, 4 hooks, 2 rules files, 1 skill.
- [ ] Agents: all `model: fable`; architect + security-reviewer `tools: Read, Grep, Glob` (read-only); coding agents get worktree isolation note + full edit tools.
- [ ] Hooks (PreToolUse python scripts, exit 2 to block): block `.env`/SSH/cloud-creds/Keychain paths, `sudo`, broad `rm -rf`, `git push`, `npm publish`/`pnpm publish`/`cargo publish`/`twine upload`, deploy commands; log all Bash commands to `.claude/hooks/command_log.jsonl`; PostToolUse format hook (ruff/prettier on edited file); Stop hook test reminder.
- [ ] settings.json wires hooks + permission deny list; no `bypassPermissions`.
- [ ] Commit.

### Task 1.1: Daemon skeleton
Files: `apps/daemon/pyproject.toml`, `src/omnimac_daemon/{main,app,config,logging_setup}.py`, `api/{health,ws}.py`, `events/bus.py`, `storage/{db,models}.py`, alembic init + first migration, tests.
Interfaces produced: `create_app() -> FastAPI`; `EventBus.publish(event: dict)/subscribe() -> AsyncIterator`; `GET /api/health -> {status:"ok", version, db:"ok"}`; `WS /ws` streams JSON events `{type, payload, ts}`.
- [ ] Failing tests: health 200 + shape; WS receives published event; JSONL log line is valid JSON with `ts, level, event`; secrets keys redacted in logs.
- [ ] Implement; alembic migration creates `tasks, audit_events, approvals, settings` tables.
- [ ] `uv run pytest` green. Commit.

### Task 1.2: Desktop shell
Files: full `apps/desktop` scaffold + `packages/design-tokens` + `packages/shared-schemas` stubs.
Interfaces produced: `api.ts` (typed fetch wrapper, `useHealth()`), `ws.ts` (auto-reconnect client → zustand), stores, 7 views routed via sidebar Layout, mocked plan/timeline data clearly labeled `MOCK_`.
- [ ] Scaffold vite react-ts; tailwind dark theme via design tokens; vendored ui components.
- [ ] src-tauri: tauri.conf points at vite dev server/dist; `shell:default` minimal capabilities.
- [ ] Command center: input + state chips (listening/planning/approval/executing) + global Stop (wired to store, daemon call stubbed until 2.x); Plan view + Timeline on mock data; Approval drawer static; Permissions/Skills/Settings static forms.
- [ ] Vitest: renders CommandCenter, state badge variants, RiskBadge levels.
- [ ] `pnpm -C apps/desktop build` + `tsc --noEmit` green. Commit.

### Task 2.1: Schemas
Files: `schemas/*.py` (all 14 contracts + enums + provenance), export script → `packages/shared-schemas/schemas/*.json` + TS types.
- [ ] Tests: plan validation rejects unknown tool names + extra args; provenance required on context objects; risk enum ordering (`R0<R1<R2<R3`); round-trip serialization.
- [ ] Commit.

### Task 2.2: State machine
- [ ] Tests: every allowed transition (parametrized over TRANSITIONS), every invalid transition raises + no state change, terminal states immutable, audit event per transition with monotonic sequence, cancellation from every non-terminal state.
- [ ] Implement `core/state_machine.py`. Commit.

### Task 2.3: Policy + injection guard
- [ ] Tests: classification per rule table; no-downgrade (step declaring R0 for R2 tool → R2); R3 denied; R1 auto only in trusted workspace; unknown tool denied; guard strips/flags directive patterns in untrusted content; untrusted content cannot alter objective/approve/expand scopes (policy inputs only from typed trusted fields).
- [ ] Implement `core/policy.py`, `core/injection_guard.py`. Commit.

### Task 2.4: Approvals
- [ ] Tests: R2 execution without approval → `ApprovalRequiredError` + `execution_blocked` audit; approve-once consumed (second use fails); deny → step fails w/o execution; approval bound to invocation id; expiry.
- [ ] Implement `core/approvals.py`. Commit.

### Task 2.5: Tool registry + mock tools
Mock tools (all clearly `MOCK`): `mock_read_file(R0)`, `mock_list_dir(R0)`, `mock_open_app(R1)`, `mock_edit_file(R1)`, `mock_send_email(R2)`, `mock_git_push(R2)`, `mock_delete_dir(R3)`, `mock_flaky(R1, fails N times then succeeds)`, `mock_slow(R0, sleeps past timeout)`.
- [ ] Tests: unknown tool, duplicate registration, invalid args (extra/missing/wrong type), timeout enforcement, cancellation mid-run, dry-run produces no side effect, redaction_fields applied.
- [ ] Implement `tools/{base,registry,mock_tools}.py`. Commit.

### Task 2.6: Verification + recovery
- [ ] Tests: VerificationResult pass/fail routing (fail → RECOVERING); retry limits per step and per task honored; policy/approval denials never retried; RecoveryDecision audited.
- [ ] Implement `core/{verification,recovery}.py`. Commit.

### Task 2.7: Audit store + redaction
- [ ] Tests: append-only (no update/delete API), strict ordering by (task_id, seq), redaction of secret keys + tool redaction_fields, events persisted to SQLite and queryable by task.
- [ ] Implement `audit/store.py`, `security/redaction.py`, repositories. Commit.

### Task 2.8: Orchestrator + task API/WS
Endpoints: `POST /api/tasks {goal, source} → Task`; `GET /api/tasks`; `GET /api/tasks/{id}` (incl. plan, steps, audit); `POST /api/tasks/{id}/cancel`; `GET /api/approvals/pending`; `POST /api/approvals/{id}/decision {approved, modified_args?}`. WS event types: `task.state_changed, task.step_started, task.step_finished, approval.requested, approval.decided, audit.appended`.
Planner: `DeterministicMockPlanner` — maps goal keywords → fixed multi-step plans over mock tools (clearly marked MOCK; `PlannerAdapter` interface ready for claude-agent-sdk in Phase 3).
- [ ] Integration tests: R0/R1-trusted task runs to COMPLETED with verification; R2 task halts at WAITING_FOR_APPROVAL, approve → COMPLETED, deny → FAILED; R3 plan → FAILED at RISK_REVIEW; cancel mid-execution → CANCELLED promptly; flaky tool recovers within retry budget; WS emits ordered task updates; no execution outside EXECUTING (attempted forced call raises).
- [ ] Commit.

### Task 2.9: Frontend wiring
- [ ] Replace mocked task flow: create task from Command Center, live plan view from WS, approval drawer answers real pending approvals (approve once / deny / modify args JSON), timeline from audit endpoint, Stop → cancel endpoint.
- [ ] Vitest: task state rendering for all 11 states; approval drawer render + decision callbacks; ws store reducer handles all event types.
- [ ] Commit.

### Task F: Completion protocol
- [ ] `uv run pytest` (all), `ruff check`, `mypy`, `pnpm lint`, `tsc --noEmit`, `vitest run`, `vite build`, `cargo check` (src-tauri, best effort).
- [ ] Update `docs/STATUS.md` + MILESTONES checkboxes; honest report: commands, pass/fail, mocked capabilities, start command, Phase 3 prompt.

## Test Matrix → Spec Requirement Mapping

| Spec requirement | Task |
|---|---|
| Allowed/invalid state transitions | 2.2 |
| Risk classification | 2.3 |
| Approval enforcement / execution without approval | 2.4, 2.8 |
| Unknown tools / invalid args | 2.1, 2.5 |
| Cancellation | 2.2, 2.5, 2.8 |
| Retry limits | 2.6 |
| Audit ordering | 2.7 |
| Secret redaction | 1.1, 2.7 |
| WebSocket task updates | 1.1, 2.8 |
| Daemon health/startup | 1.1 |
| Frontend task-state rendering | 1.2, 2.9 |
