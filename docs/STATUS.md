# THOTH status

**As of:** 2026-07-14

Phases 0–4, 5.0, 5.1, 5.2, and 5.3 are implemented. Phase 5.4's packaged native fixture, typed permission boundary, bounded semantic AX contracts/resolver/tools, independent verifiers, application-profile enforcement, focus/cancellation integration, desktop diagnostics, deterministic persona outcomes, and adversarial hardening are implemented. Phase 5.4 remains pending real TCC-backed UI capstones.

## Current verified capability

- Local inference is provider-neutral and loopback-only by default. Qwen3 4B is the measured default for the target M4/16 GB Mac; live Qwen planning, constrained JSON, and persona summary tests pass in the host context. There is no silent cloud fallback.
- The deterministic safety pipeline remains unchanged: planner output is untrusted; policy, scope, approval, execution, independent verification, recovery, and immutable audit remain separate gates. Tools execute only in `EXECUTING`.
- Every registered tool has an authoritative `FocusPolicy`. The orchestrator observes focus around execution, prevents ambiguous focus actions, verifies preservation/new focus/restoration independently, records `focus.result`, and retains failures.
- Foreground context is captured only on demand. It contains no screenshot, image, or Accessibility-tree field; titles and sensitive paths are redacted before bounded in-memory retention.
- Six versioned application profiles exist. Unknown/forbidden/undeclared capabilities fail closed. VS Code workspace association is verified through the real running bundle plus authoritative THOTH path evidence; editor read/edit remain experimental.
- Operational dialogue is in-memory, task-isolated, and expiring. It resolves only authoritative recent objects, cannot approve or expand scope, and enforces `no_push` before approval or execution.
- The desktop renders authoritative persona, foreground, workspace, focus, runtime, dialogue-expiry, and proposed/approved/executed/verified status without hidden reasoning.
- Production exposes ten dotted semantic AX tools with exact bundle/capability/target/action/verifier authority, bounded untrusted snapshots, no coordinates, fresh TCC checks, independent UI verification, modal-aware resolution, and one non-persistent diagnostic summary. All real AX capabilities remain experimental because current trust is `not_determined`.

## Verification

| Gate | Result |
|---|---|
| `uv run --project apps/daemon pytest apps/daemon/tests` | **887 passed, 1 skipped** |
| Unlocked focus rerun | 6 foreground/focus live tests passed; no skip |
| Ruff check / format | clean / 199 files formatted |
| `mypy apps/daemon/src` (strict) | clean, 108 source files |
| `pnpm -C apps/desktop test` | **68 passed** |
| Desktop ESLint / TypeScript / Vite | clean / clean / built |
| `cargo check` | passed |
| `alembic upgrade head` | passed through `0004_hash_chain` |
| `make test` | passed: **955 tests** (887 daemon + 68 desktop), plus 1 environment skip |

Host context is required for Chromium Mach ports, loopback sockets, hardware `sysctl`, NSWorkspace, and local Ollama. Sandbox-denied results are not counted as product evidence.

## Real macOS evidence

- NSWorkspace detected Finder, TextEdit, Code, Terminal, and Chrome.
- The original foreground capture identified `com.apple.loginwindow`; an
  unlocked rerun identified ChatGPT / `com.openai.codex` and passed all six
  foreground/focus live tests.
- TextEdit launched and was detected as running, but could not become frontmost while locked.
- A real background Python HTTP service ran without changing the frontmost bundle.
- The real running Code bundle matched THOTH using authoritative approved-path and task-workspace evidence; bundle/title data remained hints.
- Live Qwen3 4B inference, constrained planning, and persona-summary tests passed in the host-context full gate.
- A real Code → temporary TextEdit action → Code sequence independently
  verified final frontmost bundle `com.microsoft.VSCode`. Direct
  Finder-frontmost and TextEdit-leave-focused capstones remain pending Phase
  5.4 evidence.

See `docs/PHASE_5_2_5_3_CAPSTONE.md` for the complete matrix.

Phase 5.4 real evidence is in `docs/PHASE_5_4_CAPSTONE.md`. The fixture packaged, signed, launched, and reported its unique bundle identifier. The current real TCC probe returned false / `not_determined`, and the current desktop was locked (`loginwindow`); AX-dependent capstones therefore failed closed and no profile capability was promoted.

## Residual limits

- No voice interaction, wake word, proactivity, Gmail/Calendar control, universal app control, continuous visual awareness, or long-term memory claim.
- AX editor/document manipulation remains experimental until Accessibility permission and real evidence exist.
- Chromium foreground presentation and form operations remain experimental; only separately verified read-only/background capabilities are marked verified.
- Dialogue is process-local and intentionally disappears on restart.
- Narrow semantic Accessibility control is implemented and automated-test green but remains unverified against real UI state until explicit TCC trust and the packaged-app/TextEdit capstones pass.

## Honest capability statement

**THOTH provides a consistent local persona, understands short-lived operational context, detects the active macOS workspace, and manages supported application focus without unnecessary disruption.**

## Recommended next phase

Complete the Phase 5.4 real-evidence gate on an unlocked desktop after the user explicitly grants Accessibility trust: run the packaged-app form/delayed/ambiguity/moving workflows, exact TextEdit read-back, VS Code final-focus check, and real permission-revocation case. Promote only capabilities with independent evidence. Do not start voice, proactivity, or long-term memory first.
