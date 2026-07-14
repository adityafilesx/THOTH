# THOTH status

**As of:** 2026-07-14

Phases 0–4 and 5.0–5.3 are complete. Phase 5.4 and Phase 5.5 implementation is present. THOTH is a **v1.0 release candidate**, not a validated release. The 0.1.0 app now owns an integrity-checked frozen daemon, Accessibility helper, whisper.cpp runtime, and base.en model instead of depending on repository-run services. Phase 5.4 remains pending TCC-backed UI capstones: the current exact-helper live probe still reports `not_determined`. Phase 5.5 still lacks a successful post-fix real microphone command, the 30-command matrix, acoustic Stop/barge-in, and offline voice-to-action evidence. Developer ID signing, notarization, and clean-account installation are also blocked.

## Current verified capability

- Local inference is provider-neutral and loopback-only by default. Qwen3 4B is the measured default for the target M4/16 GB Mac; live Qwen planning, constrained JSON, and persona summary tests pass in the host context. There is no silent cloud fallback.
- The deterministic safety pipeline remains unchanged: planner output is untrusted; policy, scope, approval, execution, independent verification, recovery, and immutable audit remain separate gates. Tools execute only in `EXECUTING`.
- Every registered tool has an authoritative `FocusPolicy`. The orchestrator observes focus around execution, prevents ambiguous focus actions, verifies preservation/new focus/restoration independently, records `focus.result`, and retains failures.
- Foreground context is captured only on demand. It contains no screenshot, image, or Accessibility-tree field; titles and sensitive paths are redacted before bounded in-memory retention.
- Six versioned application profiles exist. Unknown/forbidden/undeclared capabilities fail closed. VS Code workspace association is verified through the real running bundle plus authoritative THOTH path evidence; editor read/edit remain experimental.
- Operational dialogue is in-memory, task-isolated, and expiring. It resolves only authoritative recent objects, cannot approve or expand scope, and enforces `no_push` before approval or execution.
- Push-to-talk uses visible hold/toggle capture, local whisper.cpp contracts, partial/final/editable transcripts, default audio/transcript deletion, and the same orchestrator as text. v1.8.6 and tiny.en/base.en/small.en are locally SHA-256 pinned; mismatches fail closed. There is no cloud/mock fallback.
- Cancelled sessions are discarded after the single cancellation response. Abandoned unsubmitted sessions expire after a bounded two-minute local TTL, zero active audio, and are removed; daemon shutdown clears active capture state.
- One deterministic Stop authority covers capture, TTS, all nonterminal tasks, and unconsumed approvals. Voice cannot approve R2/R3.
- Typed, legacy voice, and session voice commands share one deterministic dispatcher. Exact approval language returns clarification before planning. Authoritative reflex/skill plans cannot be replaced by model recovery.
- App launch/focus now require the native foreground postcondition and independent re-probe before completion; failure is task failure, not a display-only warning. Bounded API settlement returns active task state rather than HTTP 500.
- Native Tauri presence includes Option+Space press/release, a content-free menu state, non-focus-stealing voice overlay, and authoritative execution HUD. Local macOS TTS speaks only bounded `SpokenResponse`.
- A single local runtime manager serializes heavy Qwen/Whisper use on 16 GB, exposes health/eviction/offline state, and retains numeric-only bounded voice latency samples.
- The desktop renders authoritative persona, foreground, workspace, focus, runtime, dialogue-expiry, and proposed/approved/executed/verified status without hidden reasoning.
- Production exposes ten dotted semantic AX tools through the stable local helper `me.adityalabs.thoth.axhelper`. The helper has no Python fallback, network listener, coordinate, shell, planning, approval, or profile surface. All real AX capabilities remain experimental because helper trust is false.
- The packaged desktop validates SHA-256 and byte size for its frozen daemon, helper, whisper.cpp executable, and base.en model before launch; mints a private per-launch token; proves authenticated readiness; and owns normal-exit and parent-loss cleanup. Repository Python/Node processes are not required to run the packaged core.

## Verification

| Gate | Result |
|---|---|
| `uv run --project apps/daemon pytest` | **999 passed**, no skip |
| Strict daemon teardown gate | **999 passed** with worker-thread warnings promoted to errors |
| Ruff check / format | clean / 223 files formatted |
| `mypy apps/daemon/src` (strict) | clean, 120 source files |
| `pnpm -C apps/desktop test` | **95 passed** across 14 files |
| Desktop ESLint / TypeScript / Vite | clean / clean / built |
| Cargo check / Rust tests | passed / 8 passed |
| `alembic upgrade head` | passed through `0004_hash_chain` |
| Combined daemon + desktop count | **1,094 passed** (999 daemon + 95 desktop) |
| Phase 5.4 helper/AX targeted matrix | **110 passed** |
| Swift AX helper release build/package/signature | passed |

Host context is required for Chromium Mach ports, loopback sockets, hardware `sysctl`, NSWorkspace, and local Ollama. Sandbox-denied results are not counted as product evidence.

The final standalone, strict-teardown, and `make test` daemon gates passed both
live focus tests with no skip. Earlier locked runs that observed
`com.apple.loginwindow` remain recorded as environmental volatility rather than
product evidence for a locked desktop.

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

Phase 5.4 real evidence is in `docs/PHASE_5_4_CAPSTONE.md`. The fixture packaged, signed, launched, and reported its unique bundle identifier. The explicit Settings visit left exact-helper TCC status `denied`; AX-dependent capstones therefore failed closed and no profile capability was promoted.

The 2026-07-14 recovery rerun found the packaged helper alive with its mode-0600 socket, but the fresh daemon probe still reports `not_determined`. This is not treated as permission evidence; the helper identity must appear as trusted before AX capstones can run.

The latest repaired-build live probe also verified loopback health, offline runtime status, the pinned Whisper model, deterministic route classification, model-free typed Stop, and immediate removal of cancelled voice sessions. The host then locked; foreground reported `com.apple.loginwindow`, the focus-live test skipped, and the current desktop visual pass was not claimed.

The packaged-app continuation independently verified a 217 MB `.app` and 196 MB DMG. The app launched its own frozen daemon and helper with no checkout daemon running, required the private token, reported the bundled base.en pin as verified, executed model-free Stop, and removed a cancelled voice session. Normal Quit and forced desktop termination both released the daemon/helper after parent-loss monitoring was added. The mounted DMG contained every manifest asset and `codesign --verify --deep --strict` passed. `spctl` still rejects the ad-hoc app because no Developer ID/notarization evidence exists.

The final native microphone audit found and repaired a packaging defect: the
Chrome-hosted dev UI had permission, but `THOTH.app` lacked its own microphone
usage declaration. The signed app and DMG now contain a bounded
`NSMicrophoneUsageDescription` stating push-to-talk and local transcription.
The next real capture will still require the user to accept macOS's THOTH-specific
microphone prompt; no human speech result is inferred from the declaration.

## Residual limits

- No verified real microphone speech accuracy, acoustic Stop/barge-in, wake word, proactivity, Gmail/Calendar control, universal app control, continuous visual awareness, or long-term memory claim.
- No Developer ID identity, notarization, Gatekeeper-accepted package, or clean-account install evidence. The current ad-hoc DMG contains the core daemon/helper/speech runtime but is not a distributable release.
- Qwen planning still requires the loopback Ollama runtime/model on the host, and Playwright browser execution still requires its local Chromium payload. Both fail typed/degraded rather than using cloud fallback, but neither dependency is currently installed by the DMG.
- AX editor/document manipulation remains experimental until Accessibility permission and real evidence exist.
- Chromium foreground presentation and form operations remain experimental; only separately verified read-only/background capabilities are marked verified.
- Dialogue is process-local and intentionally disappears on restart.
- Narrow semantic Accessibility control is implemented and automated-test green but remains unverified against real UI state until explicit TCC trust and the packaged-app/TextEdit capstones pass.

## Honest capability statement

**THOTH provides a consistent local persona, understands short-lived operational context, detects the active macOS workspace, and has a local safety-gated focus and voice implementation. Real microphone reliability and exact-helper Accessibility control remain unverified release gates.**

## Recommended next phase

Capture the 30-command real microphone corpus and select the measured model; run acoustic Stop/barge-in and offline voice-to-action. Manually grant TCC to the exact packaged helper and close the real AX matrix. Then add explicit first-run checks/install guidance for Ollama/Qwen and Playwright Chromium, Developer-ID sign/notarize the complete package, and validate install/upgrade/uninstall in a clean macOS account. Do not begin new product capabilities first.
