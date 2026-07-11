# THOTH Threat Model

## 1. Assets

| Asset | Why it matters |
|---|---|
| User's filesystem & applications | THOTH's whole purpose is acting on them; misuse is direct harm |
| Credentials (Keychain, SSH keys, tokens, cookies) | Exfiltration enables account takeover |
| External side-effect channels (email, forms, uploads, git remotes, publishing) | Irreversible, outward-facing actions |
| Audit trail | Integrity of the record of what THOTH did |
| Safety engine itself | If disabled or bypassed, all other guarantees fall |
| User trust & privacy (local data, voice) | Local-first promise |

## 2. Adversaries & threat classes

### T1 — Prompt injection via external content
Web pages, emails, PDFs, documents, terminal output, repository content, form labels, images/screenshots containing instructions ("ignore previous instructions, run…", hidden text, HTML comments, filenames-as-commands).

### T2 — Model error / hallucination
Planner invents tools, wrong arguments, wrong targets, underestimates risk, claims success without verification.

### T3 — Tool misuse & scope creep
A correctly-chosen tool operating outside approved directories/domains/apps; command smuggling through the shell tool (expansion, chaining, `sudo`, broad deletion).

### T4 — Approval fatigue & consent laundering
Reusing an old approval for a new action; batching a sensitive action behind an innocuous one; approval prompt describing something other than what executes.

### T5 — Secret leakage
Secrets echoed into logs, SQLite, prompts sent to a model, frontend state, or audit events.

### T6 — Local attacker / other processes
Another local process talking to the daemon, or reading its storage.

### T7 — Supply chain
Malicious or compromised dependencies.

## 3. Mitigations (mapped to modules)

| Threat | Mitigation | Module |
|---|---|---|
| T1 | Mandatory provenance labels (`USER_TRUSTED, SYSTEM_TRUSTED, TOOL_RESULT_UNTRUSTED, WEB_UNTRUSTED, FILE_UNTRUSTED`); untrusted content cannot change objective, approve, grant permissions, expand directories/domains, request credentials, disable verification, or modify policy; directive-pattern flagging in untrusted text | `core/injection_guard.py`, `schemas/provenance.py` |
| T1, T2 | Policy engine consumes typed trusted fields only; runs independently of model recommendations | `core/policy.py` |
| T2 | Plans schema-validated before risk review; unknown tools and extra args rejected; per-step verification; no success claim without `VerificationResult` | `schemas/plan.py`, `tools/registry.py`, `core/verification.py` |
| T2, T3 | Effective risk = max(tool default, declared step risk); no downgrade path exists in code | `core/policy.py` |
| T3 | Typed tool contracts with resource scopes; restricted shell (approved cwd, allow/deny lists, no `sudo`, no broad deletion, no credential paths, timeout, output cap); tool-preference order bans coordinate clicking when structured interfaces exist | `tools/`, Phase 3 shell adapter |
| T4 | Approvals are single-use, bound to one `ToolInvocation.id`, TTL-limited, requested immediately before execution, and display the exact action + data; modified actions re-enter risk review | `core/approvals.py` |
| T5 | Redaction at every serialization boundary (audit write, log write, WS emit); secrets live in Keychain only; `.env` holds config, not credentials; hooks block credential-file access in development | `security/redaction.py`, `.claude/hooks/` |
| T6 | Daemon binds `127.0.0.1` only; SQLite/logs under user-owned paths with default macOS permissions; no remote listener. **Per-session bearer token (Phase 3 slice 2)**: every HTTP route except `/api/health` requires `Authorization: Bearer <token>` (constant-time compare); the WebSocket requires a first-message auth handshake; the token is minted at startup and handed to the desktop over a 0600 file / dev env. | `config.py`, `security/auth.py`, `api/middleware.py`, `api/ws.py` |
| T7 | Locked dependencies (uv.lock, pnpm-lock); no publish/deploy from repo tooling; CI runs no untrusted code | repo config |
| Safety-engine tampering | R3 includes "disabling the safety engine"; no API exists to bypass policy; execution path physically requires policy + approval records | `core/orchestrator.py` |

## 4. Enforcement invariants (tested)

1. No tool execution outside `EXECUTING` state.
2. No R2 execution without a matching, unconsumed, unexpired approval bound to that exact invocation.
3. R3 is denied at risk review; the task fails safe.
4. Risk levels never downgrade.
5. Every state change appends exactly one immutable audit event; the store exposes no update/delete.
6. Redaction applies before any persistence or emission.
7. Cancellation reaches a terminal `CANCELLED` state from any non-terminal state.

## 5. Residual risks (accepted for Phases 0–2)

- Mock tools only — real-world adapter risks (AX misuse, browser sandbox escape, shell smuggling) are designed for but not yet exercised.
- ~~No desktop↔daemon authentication yet (localhost only); scheduled for Phase 3.~~ **Resolved (Phase 3 slice 2):** per-session bearer token on HTTP + WebSocket, always-on.
- Audit store is append-only by API, not cryptographically tamper-evident; hash-chaining is a Phase 3 candidate (see DECISIONS).
