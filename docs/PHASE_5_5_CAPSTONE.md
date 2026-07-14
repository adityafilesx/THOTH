# Phase 5.5 capstone evidence

**Date:** 2026-07-14
**Status:** automated implementation green pending final gates; real voice evidence blocked

## Automated evidence

- Voice/text share the orchestrator and authoritative task presentation.
- whisper.cpp is the primary local provider; missing runtime/model fails typed
  unavailable with private temporary-file cleanup and no cloud fallback.
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
| Open TextEdit by spoken command | Not verified | no whisper.cpp model/microphone session |
| Continue THOTH | Not verified end-to-end | local components exist; no real spoken input |
| What am I working on | Not verified end-to-end | foreground/dialogue independently tested |
| Run tests without focus theft | Not verified by voice | background/focus contracts tested |
| Say “Thoth, stop” during task | Automated only | real speech unavailable |
| R2 by voice cannot approve | Pass automated | pending approval remains; no external effect |
| Offline voice-to-action | Not verified | external browser denial passes; Whisper absent |
| Ambiguous “Open it” | Pass automated | 409 clarification, zero new task |
| Barge in while speaking | Automated component pass | real mic/TTS acoustic loop unavailable |
| Planner disabled reflex/skill | Pass automated | model-free routing/runtime floor |

The 30-command real spoken matrix, Whisper WER/model comparison, end-to-end
latency, and memory utilisation are not available. Phase 5.5 must not be called
complete or daily-driver ready until those gates run on an unlocked desktop
with a verified local Whisper model and microphone permission.
