# Local voice and presence architecture

Phase 5.5 adds one input/output surface around the existing safety pipeline; it
does not add a voice execution engine.

```text
Option+Space / visible microphone control
  -> local MediaRecorder capture (visible state)
  -> bounded in-memory audio session + VAD
  -> whisper.cpp provider (typed unavailable if absent)
  -> partial/final/editable transcript
  -> deterministic Stop/dialogue handling or normal task submission
  -> intent / plan / policy / approval / EXECUTING tools / verification
  -> authoritative TaskPresentation + SpokenResponse
  -> local macOS say or optional local Piper
```

The native Tauri plugin owns the global press/release shortcut and emits it
only to the non-focus-stealing overlay. The overlay captures microphone audio
only after an explicit hold/toggle action, displays the active microphone,
uploads bounded chunks to loopback, releases tracks on finalise/cancel/error,
allows a three-second correction window, and submits exactly once.

The menu uses a closed status enum and never receives transcripts or secrets.
The execution HUD renders live task/policy/verification/focus state and exposes
the same global Stop endpoint as the overlay and command centre.

Audio is zeroised after transcription/finalisation/cancellation. Transcript
retention is off by default; optional retained state is in memory only and
contains no audio. There is no wake word, background listener, cloud STT, or
cloud TTS.

Voice cannot approve. A transcript is user-adjacent input and may only become a
new `TaskSource.VOICE` task. R2 remains pending in the visible invocation-bound
approval interface. Global Stop and exact whole-utterance “Omnimac, stop” bypass
the model/router/planner, interrupt speech, cancel voice sessions and tasks,
and invalidate unconsumed approvals.
