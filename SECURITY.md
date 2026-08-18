# Security Policy

OmniMac executes computer actions on behalf of the user. Its security posture is defined by the safety core described in `docs/THREAT_MODEL.md`. This file states the operational policy.

## Core guarantees

1. **Risk-gated execution.** Every action is classified R0–R3. R2 (external side effects) requires explicit single-use approval immediately before execution. R3 (destructive/sensitive) is blocked by default in the current product.
2. **No self-downgrade.** Effective risk = max(tool default, declared step risk). Neither the planner nor a tool can lower its own classification.
3. **Deterministic policy.** The policy engine consumes typed inputs only. Model output cannot approve actions, and the policy engine runs independently of model recommendations.
4. **Prompt-injection boundary.** All external content (web pages, files, emails, PDFs, terminal output, repo content, form labels, images) is labeled untrusted and cannot change objectives, approve actions, grant permissions, expand scopes, request credentials, disable verification, or modify policy.
5. **Append-only audit.** Every state change and tool invocation produces an immutable audit event.
6. **Secret handling.** Credentials live in the macOS Keychain only. Secrets are never written to SQLite, JSONL logs, prompts, or frontend state. Redaction is enforced at every serialization boundary.
7. **Restricted shell.** The shell tool requires an approved working directory, uses allow/deny lists, rejects `sudo`, broad deletion, credential paths and shell-expansion tricks, enforces timeouts and output limits, and records command, exit code, and duration.

## Reporting a vulnerability

Open a private report to the repository owner (do not file public issues for exploitable problems). Include reproduction steps and affected module. Safety-core regressions (policy bypass, approval bypass, audit gap, redaction gap, injection-boundary breach) are treated as release blockers.

## Out of scope (current phase)

Phases 0–2 ship mock tools only. Real macOS control, browser automation, shell execution, and voice are not yet wired; findings against mocks are still valuable when they demonstrate a safety-core flaw.
