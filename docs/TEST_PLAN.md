# OmniMac Test Plan

## Scope

Phases 1–2: safety core + daemon + frontend rendering. All tests run locally and in CI (`make test`). Frameworks: pytest + pytest-asyncio + httpx `ASGITransport` (daemon); vitest + @testing-library/react (desktop).

## Test matrix (spec-mandated)

| # | Requirement | Suite | File(s) |
|---|---|---|---|
| 1 | Every allowed state transition | daemon | `tests/core/test_state_machine.py` |
| 2 | Every invalid state transition (rejected, state unchanged) | daemon | `tests/core/test_state_machine.py` |
| 3 | Risk classification (R0–R3, no downgrade, unknown tool) | daemon | `tests/core/test_policy.py` |
| 4 | Approval enforcement (single-use, invocation-bound, TTL) | daemon | `tests/core/test_approvals.py` |
| 5 | Attempted execution without approval → blocked + audited | daemon | `tests/core/test_approvals.py`, `tests/test_orchestrator.py` |
| 6 | Unknown tools rejected | daemon | `tests/tools/test_registry.py` |
| 7 | Invalid tool arguments (extra, missing, wrong type) rejected | daemon | `tests/tools/test_registry.py` |
| 8 | Cancellation (state machine, mid-tool, via API) | daemon | `test_state_machine.py`, `test_registry.py`, `test_task_api.py` |
| 9 | Retry limits (per step, per task; denials never retried) | daemon | `tests/core/test_recovery.py` |
| 10 | Audit ordering (monotonic per-task sequence; append-only) | daemon | `tests/audit/test_store.py` |
| 11 | Secret redaction (logs, audit, WS) | daemon | `tests/security/test_redaction.py`, `tests/test_logging.py` |
| 12 | WebSocket task updates (ordered, typed events) | daemon | `tests/api/test_ws.py`, `tests/api/test_task_api.py` |
| 13 | Daemon health and startup | daemon | `tests/api/test_health.py` |
| 14 | Frontend rendering of task states (all 11) | desktop | `src/**/*.test.tsx` |
| 15 | Prompt-injection guard (untrusted content cannot mutate policy inputs) | daemon | `tests/core/test_injection_guard.py` |
| 16 | Schema validation (plans reject unknown tools / extra args) | daemon | `tests/schemas/test_contracts.py` |
| 17 | No execution outside EXECUTING state | daemon | `tests/test_orchestrator.py` |
| 18 | Timeout enforcement + dry-run has no side effect | daemon | `tests/tools/test_registry.py` |

## Integration scenarios (Task API, end-to-end inside daemon)

1. R0/R1 task in trusted workspace → runs to `COMPLETED`, each step verified.
2. R2 task → halts `WAITING_FOR_APPROVAL`; approve-once → `COMPLETED`; deny → `FAILED`; second use of same approval fails.
3. Plan containing R3 step → `FAILED` at `RISK_REVIEW` with audit reason.
4. Cancel during execution → `CANCELLED`, no further tool calls.
5. Flaky tool → recovers within retry budget; exhausted budget → `FAILED`.
6. WS client receives ordered `task.*`, `approval.*`, `audit.appended` events for the above.

## Quality gates (CI-enforced)

- `ruff check` + `ruff format --check` clean.
- `mypy` (strict) clean on `omnimac_daemon`.
- `eslint` + `tsc --noEmit` clean.
- `vite build` succeeds.
- No test may be weakened to pass; safety-core tests cover allowed **and** rejected paths.

## Out of scope until Phase 3

~~Real macOS automation, browser control, restricted shell, voice pipeline; their contracts are frozen (TOOL_CONTRACTS.md) and mocked here.~~ **Delivered in Phases 3–4** (below).

## Phase 4 additions (2026-07-13)

| Area | Coverage |
|---|---|
| Correlation | one id threaded task→plan→steps→invocations→results→verifications→approvals→audit (3 tests) |
| Independent verifiers | 12 verifiers unit-tested with injected probes; fail-closed availability (composite-any + EXIT_CODE self-certification regressions); malformed params fail closed; orchestrator integration: tool-ok + failed probe ⇒ never verified |
| Bounded recovery | retry/replan/escalate budgets, depth cap, denials untouched; replan cycle re-enters policy review; 25-execution cap; `FAILED_REQUIRES_USER` terminal |
| Audit hash chain | linkage, deterministic recompute, raw-SQL tamper + deletion detection, per-task independence, API manifest |
| AX | mock adapter ops, TCC permission gate, tool risks/scopes, dry-run inertness, registry scope backstop |
| Browser interaction | two-phase submission (single-use, unknown, stale-form, stale-action-host), current_url anchor check, injection containment, off-domain refusal, REAL Playwright file:// round-trip |
| Skill engine | expansion/substitution, input rejection, **no-downgrade** pipeline proof, seed idempotency, run endpoint E2E |
| Voice | STT mock + typed unavailable error, TTS interrupt timing + new-speak-interrupts, LIVE `say -o` render, transcript-cannot-approve isolation |
| Planner evals | expectation checks, exception-as-failure, redaction-by-construction reports |
| Capstones | harness completion + independent final-state verification, failure reporting, R2 approval recording; five REAL runs (docs/CAPSTONE_REPORT.md) |

Gate at Phase 4 close: **daemon 551 passed, desktop 56 passed; ruff, mypy --strict, eslint, tsc, vite build clean; alembic single head (0004).**
