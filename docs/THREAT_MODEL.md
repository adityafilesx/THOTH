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
| T3 | Typed tool contracts with resource scopes; **restricted shell implemented** (`shell_run`: allowlisted bare-name executables, no shell interpretation / metacharacters rejected, `requested_scope` contains cwd + every argument path so the scope enforcer refuses out-of-scope/denylisted paths, R2 approval per command, timeout, 32 KiB output cap, minimal env, no `sudo`/broad-delete/credential paths); tool-preference order bans coordinate clicking when structured interfaces exist | `tools/shell_tool.py`, `security/shell_policy.py`, `core/scope.py` |
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

- ~~Mock tools only — real-world adapter risks (AX misuse, browser sandbox escape, shell smuggling) are designed for but not yet exercised.~~ **Resolved (Phases 3–4):** real adapters shipped behind the same contracts; see §6.
- ~~No desktop↔daemon authentication yet (localhost only); scheduled for Phase 3.~~ **Resolved (Phase 3 slice 2):** per-session bearer token on HTTP + WebSocket, always-on.
- ~~Audit store is append-only by API, not cryptographically tamper-evident; hash-chaining is a Phase 3 candidate (see DECISIONS).~~ **Resolved (Phase 4 slice 9):** per-task SHA-256 hash chain + `verify_chain` manifest (ADR-022).

## 6. Phase 3–4 surfaces (added 2026-07-13)

New attack surfaces and their mitigations; the §4 invariants all still hold and are tested.

| Surface | Threats | Mitigations |
|---|---|---|
| Scoped filesystem / restricted shell / git tools | path escape, sensitive-file reads, argv injection | symlink-safe resolution + denylist; ScopeEnforcer gate + registry backstop; allowlisted bare-name argv, `shell=False`, metacharacters rejected; R2 per-command approval |
| Accessibility (AX) tools | driving un-approved apps; hostile AX values steering the agent; unstable TCC identity | `requested_scope(apps=[app])` enforced; role+label addressing (no coordinates); AX values are untrusted inert data; exact helper `me.adityalabs.thoth.axhelper` over mode-0600 peer-UID-authenticated Unix socket; no Python fallback; every real call freshly TCC-gated |
| Interactive browser session | hostile page content (prompt injection), off-allowlist navigation, deceptive form submission | page text always `WEB_UNTRUSTED` + injection-guard scanned (containment tested); per-navigation domain scope; **two-phase submission**: prepare captures the exact payload, submit is R2 + single-use, refuses stale forms AND action hosts differing from the approved `action_url`; `current_url` scope anchors must match the session's actual page |
| Skill engine | a skill smuggling lowered risks / extra tools / removed verification | planning-only expansion; declared risk copied verbatim (effective = max(default, declared) — downgrade attempt still halts for approval, tested); expanded plans re-enter full validation + policy review; typed input validation |
| Voice | transcript/replay approval, embedded Stop, TTS feedback, hidden recording, duplicate tasks, audio/secret retention | visible push-to-talk only; voice never consumes approval; whole-utterance model-free Stop excludes TTS; edit/final submit-once; tracks/audio zeroised; local STT typed unavailable; bounded `SpokenResponse` suppresses secrets; no cloud fallback |
| Local speech supply chain | replaced runtime/model weights, filename spoof, silent provider substitution | optional expected SHA-256 for executable and model is recomputed before transcription; mismatch fails typed unavailable; registry is inert data; no cloud/mock fallback |
| Audit tampering (around the store) | direct SQLite edits rewriting history | per-task hash chain over prev-hash+task+correlation+seq+type+payload+timestamp; `verify_chain` detects mutation, deletion (seq gap), reorder; store still has no update/delete surface |
| Recovery loops | runaway retry/replan cycles | ≤2 retries/step, ≤2 replans, depth ≤3 episodes, ≤25 executions/task; exhaustion ⇒ terminal `FAILED_REQUIRES_USER` |
| Packaged local runtime | replaced daemon/helper/model, inherited secrets, orphaned services, unauthenticated loopback peer | signed app resources plus versioned size/SHA-256 manifest; fail-closed Rust validation; fresh mode-0600 bearer token; minimal child environments; authenticated readiness probe; explicit normal-exit shutdown plus child parent-loss monitors |

### Residual risks (accepted for Phase 4)

- The live planner path (planning-only Anthropic Messages call) is built but unverified without an API key; plan output remains untrusted and fully re-validated regardless.
- AX element interaction and STT are pending the Accessibility permission and a local model + microphone respectively; both fail closed today.
- A secret typed into a shell argument or commit message is recorded in audit (mitigated by per-command approval; documented in ADR-014/015).
- Harness capstone approvals are granted programmatically (recorded as simulated-human); live capstones will use real human approvals.

## 7. Phase 5.2–5.3 context and presentation surfaces

| Surface | Threat | Mitigation |
|---|---|---|
| Persona/local summary | false success, target mutation, approval pressure, tool/risk directives | post-verification frozen facts; deterministic safety-sensitive wording; local summary validates success, counts, named targets, and directives; deterministic fallback; no tool interface |
| Foreground/window context | title injection, sensitive titles/paths, continuous surveillance | on-demand snapshots; untrusted hints; redaction before bounded in-memory retention; no screenshot/image/full AX-tree field |
| Focus management | background focus theft, model focus downgrade, false restoration claim | registered policy authority; execution-bound snapshot; ambiguous action runs nothing; independent final-frontmost verification; immutable audit; failures retained |
| Application profiles | model/page self-expansion, target/action/verifier substitution, forbidden-operation downgrade | private copied versioned profiles; exact tool/action/verifier target rules at plan, registry, and resolved-element boundaries; unknown/undeclared/forbidden fail closed; experimental requires trusted opt-in; verified requires verifier mapping + real date |
| Semantic AX focus/cancellation | focus before permission validation, restore before UI verification, mutation after cancellation | snapshot then fresh profile/TCC validation; bundle-bound temporary focus; independent UI probe before restoration; ordered audit; shared cancellation flag checked before mutation; synchronous AX message treated as an atomic non-rollbackable unit |
| Accessibility diagnostics | raw UI-tree exposure, secure value leakage, fixture data presented as live | live permission/profile endpoint; single in-memory semantic snapshot; labels/values/windows/elements excluded; advanced evidence behind developer toggle; explicit-only Settings action |
| Accessibility persona | model/AX text claiming false success, mutating a target, or hiding failed verification | closed deterministic outcome enum; bundle-ID display-name allowlist; planner titles and raw AX prose never echoed; verified wording requires independent per-step verification and focus evidence |
| Workspace association | title spoof, symlink escape, stale/removed workspace | approved paths/task workspace are authority; bundle/title hints only; normalization and symlink containment; stale/missing/ambiguous fail safely |
| Operational dialogue | approval replay, scope expansion, stale/cross-task reference, push despite constraint | task isolation + TTL + authoritative objects; vague approval rejected; approved workspace set required; `no_push` checked before approval/execution; restart drops state |

### Residual risks after Phase 5.3

- The locked desktop prevented real final-focus/restoration evidence in this run; code fails closed and the live test skips with the precise `loginwindow` reason.
- AX editor/document manipulation remains experimental until explicit Accessibility permission and a real verification pass.
- Dialogue is deliberately volatile; restart loses short follow-up context rather than persisting sensitive operational memory.
- Local-model availability depends on the loopback runtime. Model-dependent requests degrade deterministically; no cloud fallback is attempted.

### Residual risks after Phase 5.5 implementation

- Real Whisper accuracy, microphone/global-shortcut behaviour, acoustic
  echo/barge-in, end-to-end latency, and memory pressure with Qwen loaded are
  unverified because no local Whisper runtime/model is installed and the
  desktop is locked.
- The AX helper development artifact is ad-hoc signed. Release packaging needs
  a stable Developer ID signature before manual TCC approval is production
  evidence.
- The current desktop DMG is ad-hoc and Gatekeeper rejects it. Strict bundle
  and manifest verification now pass and the core daemon/helper/base.en assets
  are present, but Developer ID/notarization and clean-account evidence remain
  mandatory. Ollama/Qwen and Playwright Chromium are still host prerequisites.
- Unix socket peer-UID authentication prevents other users but not a malicious
  same-user process. The helper's deliberately tiny protocol and upstream
  profile/policy gates reduce impact; code-signature-bound XPC remains a future
  hardening option.
