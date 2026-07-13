# THOTH

**A local-first, voice-enabled macOS computer operator.** THOTH converts user intentions into safe, inspectable, and verified computer actions.

THOTH is not a chatbot, a note-taking app, a generic second brain, or a voice-command launcher. It is an autonomous operator with a deterministic safety core:

> User request → intent normalization → structured plan → policy review → approval if needed → tool router → execution → verification → result or bounded recovery.

## Status

**Phases 0–3 complete; Phase 4 built (live-planner runs pending an API key).** The deterministic safety core is real and enforced end-to-end: risk policy (R0–R3, no downgrades), single-use invocation-bound approvals, scoped tool execution only in `EXECUTING`, twelve independent post-execution verifiers (fail-closed when a probe is unavailable), bounded recovery (retries → replans → `FAILED_REQUIRES_USER`), and a tamper-evident audit hash chain. Real capabilities behind the same contracts: scoped filesystem, restricted shell, git, macOS app launch/focus, Accessibility element tools (element interaction pending the TCC permission), interactive browser sessions with two-phase form submission (`prepare` → explicit R2 approval of the exact payload → `submit`), a planning-only skill engine with five built-in skills, and push-to-talk voice adapters (STT pending a model + microphone; interruptible `say` TTS verified).

Five capstone workflows ran against the real OS and were **independently verified** — real file and git state, a real `https://example.com` fetch, a real single-use approval, a real TextEdit launch ([docs/CAPSTONE_REPORT.md](docs/CAPSTONE_REPORT.md)). Those runs used scripted reference plans; the same goals through the **live Claude planner are pending live verification** (requires `ANTHROPIC_API_KEY`).

Maximum supported claim: **THOTH can safely execute and verify selected multi-step workflows across approved local applications, files, Git repositories and browser environments.** It does not claim general autonomous computer control. See [docs/STATUS.md](docs/STATUS.md).

## Principles (priority order)

1. Safety over autonomy
2. Reliability over feature count
3. Structured tools over screen coordinates
4. Verification over assumption
5. Local processing over cloud processing where practical
6. Explicit user control over hidden background behavior
7. Typed contracts over free-form agent output
8. Small independently testable modules over a monolithic agent
9. No destructive action without explicit authorization
10. No external side effect based only on previously granted general permission

## Repository layout

```
apps/desktop        Tauri 2 + React + TypeScript desktop client
apps/daemon         Python 3.12 FastAPI daemon (agent core, safety engine)
packages/shared-schemas   JSON Schemas + TS types generated from Pydantic contracts
packages/design-tokens    Design tokens for the desktop UI
docs                PRD, architecture, threat model, test plan, decisions, status
.claude             Claude Code agents, hooks, rules, skills
```

## Prerequisites

- macOS (Apple Silicon or Intel)
- [uv](https://docs.astral.sh/uv/) (manages Python 3.12 automatically)
- Node.js ≥ 20 with corepack (`corepack enable pnpm`)
- Rust toolchain (for the Tauri shell)

## Quick start

```bash
make setup      # install daemon + desktop dependencies
make dev        # start daemon (:7710) and desktop dev server together
```

Or individually:

```bash
make daemon     # FastAPI daemon on http://127.0.0.1:7710
make desktop    # Vite dev server (browser) — or: cd apps/desktop && pnpm tauri dev
```

## Testing

```bash
make test       # daemon (pytest) + desktop (vitest)
make lint       # ruff + eslint
make typecheck  # mypy + tsc
```

## Risk model (summary)

| Level | Meaning | Behavior |
|---|---|---|
| R0 | Read-only | Auto-runs inside approved boundaries |
| R1 | Reversible local action | Auto-runs only in a trusted workspace |
| R2 | External side effect | Explicit approval immediately before execution |
| R3 | Destructive / highly sensitive | Blocked by default |

No planner or tool may downgrade its own risk level. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Documentation

- [docs/PRD.md](docs/PRD.md) — product requirements
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — module map and execution flow
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) — assets, adversaries, mitigations
- [docs/TOOL_CONTRACTS.md](docs/TOOL_CONTRACTS.md) — tool contract requirements
- [docs/PRIVACY.md](docs/PRIVACY.md) — local-first data handling
- [docs/TEST_PLAN.md](docs/TEST_PLAN.md) — test matrix
- [docs/MILESTONES.md](docs/MILESTONES.md) — phase checklists
- [docs/DECISIONS.md](docs/DECISIONS.md) — architecture decision records
- [docs/STATUS.md](docs/STATUS.md) — honest current state

## Security

See [SECURITY.md](SECURITY.md). Secrets never live in SQLite, logs, prompts, or frontend state; credentials belong in the macOS Keychain.
