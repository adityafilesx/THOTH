# Phase 5.5 implementation audit

**Date:** 2026-07-14  
**Branch:** `phase-5/persona`  
**Starting commit:** `93ec2c3` (`docs(phase-5.4): record capstone limits`)

## Repository state

The tracked working tree was clean at takeover. The only entries reported by
`git status --short` were the pre-existing untracked `.agents/` and `.codex/`
directories. They are user/Codex metadata, are outside the implementation
scope, and must remain untouched. `git diff`, `git diff --cached`, and
`git stash list` were empty. No remote operation was performed.

The Phase 5.4 commit series from `166999e` through `93ec2c3` is present and
intact. The existing semantic Accessibility implementation, profile gates,
verification, focus/cancellation integration, deterministic persona output,
desktop diagnostics, resource ceilings, adversarial tests, and native test
fixture are therefore preserved rather than regenerated.

## Measured starting baseline

The baseline was rerun before any production change:

| Gate | Result |
|---|---|
| Daemon tests | **888 passed** in 31.68 seconds; one third-party deprecation warning |
| Desktop tests | **68 passed** across 9 files in 1.86 seconds |
| Aggregate | **956 passing tests** |

This differs from the handoff's expected 887 passes plus one skip: the current
checkout collected and passed all 888 daemon tests. Static analysis and build
gates were green at the Phase 5.4 handoff and will be rerun after implementation.

## Remaining Phase 5.4 evidence

The implementation is complete, but real Accessibility evidence remains open.
The exact process currently calling `AXIsProcessTrusted()` is:

| Property | Observed value |
|---|---|
| Process | uv-managed CPython 3.12.13 (`python3`) |
| Virtual-environment path | `/Users/aditya1981/Downloads/OmniMac/.venv/bin/python3` |
| Resolved executable | `/Users/aditya1981/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/bin/python3.12` |
| Bundle identifier | None |
| Signing | ad-hoc, linker-signed; no team identifier or bound Info.plist |
| Accessibility trust | `false` |
| Stability | Not stable enough for production TCC identity |
| Production-intended | No; it is a development interpreter |

The macOS session still reports `loginwindow` / `com.apple.loginwindow` as the
frontmost process. Consequently the real fixture workflow, TextEdit exact AX
read-back, delayed/ambiguous/moving element exercises, modal exercise, and real
permission-revocation capstone cannot be truthfully closed in this environment.
The earlier unlocked Code → TextEdit → Code focus restoration remains valid
evidence, but is not evidence for the current Python TCC host.

A production-stable helper identity is required before asking the user for TCC
trust. It must be a narrow local helper with bundle identifier
`me.adityalabs.omnimac.axhelper`, authenticated restrictive local IPC, the
existing typed AX operations only, and no planning, approval, shell, coordinate,
profile expansion, or instruction interpretation surface. Manual TCC approval
and an unlocked desktop remain user-controlled gates; this run must not modify
TCC or automate permission granting.

## Existing voice interfaces worth preserving

- `voice/stt.py` already defines a small async adapter boundary, typed
  unavailability, deterministic mock, and delete-after-transcription temp-file
  behaviour. Its faster-whisper implementation is unverified and is not the
  requested primary provider.
- `voice/tts.py` already supplies interruptible, argv-only `/usr/bin/say`
  playback with terminate/kill fallback. A live silent AIFF render is tested.
- `api/voice.py` already exposes transcribe, voice-task, say, and interrupt
  endpoints. Voice text enters the normal orchestrator as `TaskSource.VOICE`.
- An adversarial API test proves a transcript saying "approve the pending
  action" creates a separate task and leaves the original approval pending.
- The orchestrator, intent router, operational dialogue store, deterministic
  persona composer, spoken response preview, focus manager, foreground broker,
  application profiles, and task presentation API are reusable safety and
  integration boundaries.
- The desktop already has live task/event state, operational presentation,
  execution stages, focus/runtime display, and a visible global Stop control.
  The command-centre microphone button is still a disabled placeholder.
- Tauri is a minimal shell. It has no tray, global shortcut, microphone capture,
  voice overlay, or native runtime-status bridge yet.

## Local host/runtime findings

The host is a 16 GB Apple M4 MacBook Air with 10 CPU cores, running macOS 26.3
on battery power at audit time. Qwen3 4B remains available through the existing
local inference path. `/usr/bin/say` is available and already live-tested.

No `whisper-cli`, `whisper-cpp`, `whisper`, `ffmpeg`, or `sox` executable was
found, Homebrew reported no installed `whisper-cpp` package, and no local
`ggml-*.bin`/Whisper model was found in the bounded application-support, cache,
local-share, or Homebrew-share search. Therefore real Whisper model selection,
30 spoken-command evaluation, and microphone latency measurements cannot pass
until a local whisper.cpp runtime and model are installed and the interactive
desktop/microphone are available. The implementation must expose typed
unavailability and never substitute cloud speech.

## Missing Phase 5.5 components

1. Provider-neutral speech-recognition contracts, whisper.cpp adapter, health,
   cancellation, bounded partial/final lifecycle, VAD state, and privacy-led
   audio/transcript retention.
2. Audio-capture session and editable correction-window state shared by global
   push-to-talk and the command centre without creating a second execution
   engine.
3. Provider-neutral speech synthesis, macOS native provider, optional typed
   Piper provider, segmented spoken-response playback, voice/speed settings,
   non-verbal cues, and deterministic barge-in.
4. A single deterministic stop authority covering listening, transcription,
   planning, approval wait, execution, verification, recovery, and speaking;
   cancellation must invalidate approvals. The stop phrase must bypass routing,
   skills, planning, and model inference.
5. Unified Qwen/Whisper/TTS runtime state, concurrency and memory policy,
   on-demand loading, idle eviction, failure recovery, integrity/health, battery
   mode, and offline state.
6. Native global hold/toggle shortcut and menu-bar state, visible microphone
   indication, compact editable voice overlay, and live execution HUD.
7. Offline/adversarial integration tests, latency/resource instrumentation,
   real command matrix, capstone evidence, and truthful documentation.

## Continuation sequence

Changes will use test-driven, small local commits:

1. Record this audit and immediately available TCC-host evidence.
2. Add failing tests, then implement local STT contracts, whisper.cpp typed
   provider, transcript/VAD/capture lifecycle, privacy deletion, and stop-phrase
   matching.
3. Add deterministic global stop/approval invalidation and barge-in across the
   daemon lifecycle.
4. Add TTS provider contracts and the local macOS/Piper boundaries, then the
   unified local runtime manager and offline/concurrency policy.
5. Add Tauri global shortcut/menu-bar state and desktop overlay/HUD against live
   daemon state, without exposing transcripts in the menu or stealing focus.
6. Integrate persona spoken output and dialogue continuity; add security,
   resource, offline, and duplicate-submission coverage.
7. Run every automated gate, run only available real capstones, measure rather
   than infer latency/resource values, update ADRs and phase documentation, and
   withhold Phase 5.5 completion wherever a real criterion remains unverified.

## Claim ceiling during implementation

Automated contracts are not evidence that global push-to-talk, real local STT,
or broad spoken-command accuracy works on this host. Until the real microphone,
Whisper model, global-shortcut, offline, and 30-command gates pass, Phase 5.5 is
implementation-in-progress and no new voice capability claim is made.

## Implemented continuation outcome

The audit findings were preserved. Subsequent local commits added the
whisper.cpp provider/contracts, in-memory partial/final/edit lifecycle,
deterministic global Stop and approval invalidation, local macOS/Piper TTS,
bounded runtime manager, native shortcut/menu/overlay/HUD, authoritative
persona playback, safe recent dialogue resolution, numeric latency metrics,
and tool-level offline browser refusal. The unstable Python AX host was
replaced by `me.adityalabs.omnimac.axhelper`; a live mode-0600 socket/trust probe
passed structurally and returned false as expected.

Real Whisper, microphone, 30-command, offline voice-to-action, unlocked global
shortcut, and TCC-backed AX workflows remain unavailable. The original claim
ceiling therefore remains in force until those external evidence gates pass.
