# OmniMac Architecture

## 1. System overview

Two processes, one machine:

```
┌────────────────────────────┐        HTTP + WebSocket        ┌──────────────────────────────────┐
│  apps/desktop (Tauri 2)    │ ─────────────────────────────▶ │  apps/daemon (FastAPI, py3.12)   │
│  React UI, thin client     │ ◀───────────────────────────── │  agent core + safety engine      │
└────────────────────────────┘         event stream           └──────────────────────────────────┘
                                                                │ SQLite (tasks/plans/approvals/
                                                                │         events/skills/settings)
                                                                │ JSONL structured logs
                                                                │ macOS Keychain (secrets only)
```

The desktop app holds no business logic and no secrets; it renders daemon state and forwards user intent/decisions.

## 2. Required execution flow

```
User request → intent normalization → structured plan → policy review
  → approval if needed → tool router → execution → verification
  → result or bounded recovery
```

The **planner never directly executes tools**. Tool execution happens only inside the orchestrator's `EXECUTING` state via the tool router.

## 3. Daemon modules

| Module | Path (`src/omnimac_daemon/`) | Responsibility |
|---|---|---|
| API gateway | `api/` | REST endpoints; request validation; no business logic |
| WebSocket event stream | `api/ws.py`, `events/bus.py` | In-process async pub/sub fanned out to WS clients |
| Agent orchestrator | `core/orchestrator.py` | Drives a task through the state machine; owns the loop |
| Planner | `core/planner.py` | `PlannerAdapter` interface; Phase 2 ships `DeterministicMockPlanner`; Phase 3 adds claude-agent-sdk implementation. Output validated against `ExecutionPlan` schema before risk review |
| Task state machine | `core/state_machine.py` | Deterministic transitions; audit event per change |
| Risk & policy engine | `core/policy.py` | R0–R3 classification; runs independently of model output; typed inputs only |
| Approval engine | `core/approvals.py` | Single-use, invocation-bound, TTL-limited approvals |
| Prompt-injection guard | `core/injection_guard.py` | Provenance labeling; untrusted-content firewall |
| Tool registry | `tools/registry.py` | Typed tool contracts; unknown names/args rejected |
| Verification engine | `core/verification.py` | Per-step verification strategies; `VerificationResult` |
| Recovery controller | `core/recovery.py` | Bounded retries; never retries denials |
| Skill engine | (Phase 3) | Declarative skill workflows |
| Voice pipeline | (Phase 3) | Push-to-talk STT abstraction; `say` TTS adapter |
| Storage layer | `storage/` | SQLAlchemy 2 async models + repositories; Alembic |
| Audit & observability | `audit/store.py`, `logging_setup.py` | Append-only audit store; JSONL logs; redaction |
| macOS adapters | (Phase 3) | PyObjC/AX; AppleScript/JXA behind typed adapters |
| Browser adapters | (Phase 3) | Playwright MCP |
| Shell adapters | (Phase 3) | Restricted subprocess execution |
| Filesystem adapters | (Phase 3) | Scoped, approved-directory file operations |

Phase 3 modules exist today only as interfaces/mocks; they are listed so boundaries are fixed now.

## 4. Task state machine

States: `RECEIVED, UNDERSTANDING, PLANNING, RISK_REVIEW, WAITING_FOR_APPROVAL, EXECUTING, VERIFYING, RECOVERING, COMPLETED, FAILED, CANCELLED`.

```
RECEIVED → UNDERSTANDING → PLANNING → RISK_REVIEW ─┬─▶ EXECUTING ⇄ VERIFYING → COMPLETED
                                                   └─▶ WAITING_FOR_APPROVAL ─▶ EXECUTING
EXECUTING → RECOVERING → EXECUTING | FAILED
EXECUTING → WAITING_FOR_APPROVAL          (later step needs approval)
VERIFYING → RECOVERING                    (verification failed)
any non-terminal → CANCELLED | FAILED
```

Rules: transitions validated against an explicit table; invalid transitions raise and change nothing; every accepted transition emits an immutable `AuditEvent` with a per-task monotonic sequence number; **no tool execution outside `EXECUTING`** (enforced in the executor, not by convention).

## 5. Data contracts

All cross-boundary payloads are Pydantic v2 models (`schemas/`): `Task, ExecutionPlan, PlanStep, ToolDefinition, ToolInvocation, ToolResult, VerificationResult, ApprovalRequest, ApprovalDecision, AuditEvent, SkillDefinition, WorkspaceProfile, PolicyDecision, RecoveryDecision`. Externally-supplied payloads use `extra="forbid"`. Plans are schema-validated before risk review; unknown tool names and extra arguments are rejected. JSON Schemas + TS types are exported to `packages/shared-schemas` so the frontend shares the same contracts.

## 6. Event model

`EventBus` is an in-process asyncio pub/sub. Emitters: state machine, orchestrator, approval engine, audit store. WS event envelope:

```json
{ "type": "task.state_changed", "ts": "2026-07-11T12:00:00Z", "payload": { ... } }
```

Types: `task.created, task.state_changed, task.step_started, task.step_finished, approval.requested, approval.decided, audit.appended`. All payloads pass redaction before serialization.

## 7. Provenance & injection boundary

Every context object carries a provenance label: `USER_TRUSTED, SYSTEM_TRUSTED, TOOL_RESULT_UNTRUSTED, WEB_UNTRUSTED, FILE_UNTRUSTED`. Untrusted content cannot: change the objective, approve actions, grant permissions, expand approved directories/domains, request credentials, disable verification, or modify policy. The policy engine's inputs are typed fields from trusted objects only — never free text from untrusted sources. See THREAT_MODEL.md.

## 8. Tool-selection policy

Preference order enforced by the tool router: (1) official API/MCP → (2) browser DOM automation → (3) application CLI or restricted shell → (4) macOS Accessibility elements → (5) screenshot+coordinates. Coordinate clicking is forbidden when a structured interface exists.

## 9. Persistence

- **SQLite** (`aiosqlite`, Alembic-migrated): tasks, plans (serialized on task), approvals, audit events, skills, settings.
- **JSONL logs**: one structured line per event; rotated by day; redacted at write.
- **Keychain**: the only home for credentials. Never SQLite, logs, prompts, or frontend state.

## 10. Frontend architecture

React 18 + Vite; Zustand stores (`connection`, `tasks`, `ui`); TanStack Query for REST reads; a single reconnecting WS client dispatches typed events into stores. Views: CommandCenter, PlanView, ApprovalDrawer, Timeline, Permissions, Skills, Settings. Tauri 2 provides the shell (no custom Rust commands in Phases 0–2; IPC surface deliberately minimal).
