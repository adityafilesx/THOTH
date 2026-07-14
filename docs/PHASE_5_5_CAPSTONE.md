# Phase 5.5 capstone evidence

**Date:** 2026-07-14
**Status:** pinned local runtime green; real microphone evidence blocked

## Automated evidence

- Voice/text share the orchestrator and authoritative task presentation.
- whisper.cpp v1.8.6 and tiny.en/base.en/small.en are locally installed and
  SHA-256 pinned. Binary/model mismatch fails typed unavailable before use.
- Partial/final/edit/correction/submit-once/cancel/audio-zeroisation contracts
  pass with the explicit mock provider.
- Exact whole-utterance Stop bypasses intent/planner, cancels sessions/tasks/TTS,
  and invalidates unconsumed approvals. Embedded webpage/TTS phrases do not.
- macOS local speech uses bounded `SpokenResponse`; secrets and secure paths are
  suppressed; interruption is below the component target.
- Native global shortcut, tray state, overlay, visible microphone state, and
  execution HUD compile and pass React/Rust tests.
- Unique recent voice follow-ups resolve; multiple contexts require
  clarification; vague approval creates no authorization.
- Network isolation rejects external browser operations before adapter I/O and
  preserves loopback/local capability.

## Required live matrix

| Capstone | Result | Reason/evidence ceiling |
|---|---|---|
| Open TextEdit by spoken command | Not verified | runtime exists; no real microphone session |
| Continue THOTH | Not verified end-to-end | local components exist; no real spoken input |
| What am I working on | Not verified end-to-end | foreground/dialogue independently tested |
| Run tests without focus theft | Not verified by voice | background/focus contracts tested |
| Say “Thoth, stop” during task | Automated only | no real acoustic trial |
| R2 by voice cannot approve | Pass automated | pending approval remains; no external effect |
| Offline voice-to-action | Not verified | external browser denial passes; no real microphone workflow |
| Ambiguous “Open it” | Pass automated | 409 clarification, zero new task |
| Barge in while speaking | Automated component pass | real mic/TTS acoustic loop unavailable |
| Planner disabled reflex/skill | Pass automated | model-free routing/runtime floor |

All candidates passed a bundled-WAV health probe; base.en produced one managed
partial/final/edit/cancel run with no residual temp file. This does not select
a production model. The 30-command real spoken matrix, real WER/intent/model
comparison, acoustic Stop/barge-in, and installed-build latency are not
available. Phase 5.5 must not be called complete or daily-driver ready until
those gates run on an unlocked desktop
with a verified local Whisper model and microphone permission.

## Final automated gates

| Gate | Result |
|---|---|
| Daemon | 958 passed, no skip |
| Desktop | 75 passed across 12 files |
| Ruff / format | clean / 219 files |
| Strict mypy | clean / 118 source files |
| ESLint / TypeScript / Vite | clean / clean / built |
| Cargo check / Rust tests | passed / 1 passed |
| Swift helper release/package/signature | passed |
| Alembic fresh database | upgraded through `0004_hash_chain` |
| Phase 5.4 helper/AX targeted matrix | 110 passed |
| `make test` | 1,033 passed, no skip |
