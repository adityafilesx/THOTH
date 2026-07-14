# THOTH

**A local-first macOS computer operator.** THOTH converts user intentions into safe, inspectable, and verified computer actions.

THOTH is not a chatbot, a note-taking app, a generic second brain, or a voice-command launcher. It is an autonomous operator with a deterministic safety core:

> User request → intent normalization → structured plan → policy review → approval if needed → tool router → execution → verification → result or bounded recovery.

## Status

**THOTH is a v1.0 release candidate, not a validated release.** The deterministic safety core is enforced end to end: no tool execution outside `EXECUTING`, no risk downgrade, invocation-bound single-use approvals, scoped tools, independent verification, bounded recovery, and tamper-evident audit. A local SHA-256-pinned whisper.cpp v1.8.6 runtime plus tiny.en/base.en/small.en candidates are installed on the validation host, and bundled-sample transcription works. Real microphone accuracy, acoustic Stop/barge-in, TCC-backed AX mutations, notarized packaging, and clean installation remain unvalidated.

Five capstone workflows ran against the real OS and were **independently verified** — real file and git state, a real `https://example.com` fetch, a real single-use approval, a real TextEdit launch ([docs/CAPSTONE_REPORT.md](docs/CAPSTONE_REPORT.md)). Those runs used scripted reference plans; the same goals through the **live Claude planner are pending live verification** (requires `ANTHROPIC_API_KEY`).

Current bounded claim: **THOTH provides a consistent local persona, understands short-lived operational context, detects the active macOS workspace, manages supported application focus, and has a fully local voice/presence implementation pending real speech-model evaluation.** It does not claim verified broad speech accuracy, proactivity, universal app control, continuous visual awareness, or long-term memory. See [docs/STATUS.md](docs/STATUS.md) and [Phase 5.5 capstones](docs/PHASE_5_5_CAPSTONE.md).

See [the v1 release report](docs/V1_RELEASE_REPORT.md) for exact runtime hashes,
test results, packaging evidence, and mandatory release blockers.

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
apps/ax-helper      Stable signed macOS Accessibility host (local Unix socket)
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
- Optional for real voice: local `whisper-cli` plus a SHA-256-pinned GGML Whisper model

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
- [docs/PERSONA_EVALUATION.md](docs/PERSONA_EVALUATION.md) — persona safety/evaluation evidence
- [docs/APPLICATION_PROFILES.md](docs/APPLICATION_PROFILES.md) — supported app capability authority
- [docs/ACCESSIBILITY_ARCHITECTURE.md](docs/ACCESSIBILITY_ARCHITECTURE.md) — semantic AX authority, bounds, and responsibilities
- [docs/PHASE_5_4_CAPSTONE.md](docs/PHASE_5_4_CAPSTONE.md) — real permission/fixture evidence and blocked capstones
- [docs/VOICE_ARCHITECTURE.md](docs/VOICE_ARCHITECTURE.md) — local voice, Stop, presence, and retention boundaries
- [docs/PHASE_5_5_CAPSTONE.md](docs/PHASE_5_5_CAPSTONE.md) — automated evidence and remaining real voice gates

## Security

See [SECURITY.md](SECURITY.md). Secrets never live in SQLite, logs, prompts, or frontend state; credentials belong in the macOS Keychain.
