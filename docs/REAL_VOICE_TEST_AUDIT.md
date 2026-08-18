# OmniMac real voice test recovery audit

Date: 2026-07-14  
Branch: `phase-5/persona`  
Starting commit: `f47a915 docs: publish v1 release report`

## Scope

This run is limited to real microphone and voice-path validation. It does not include signing, notarization, packaging, new integrations, new product features, or unrelated Accessibility work. Real-user microphone evidence will only be recorded when the user personally speaks the command.

## Repository starting state

- The tracked working tree was clean at the start of this run.
- `.agents/` and `.codex/` were the only untracked paths. They are local support directories and will be preserved.
- `git diff` and `git diff --cached` were empty.
- `git stash list` was empty.
- No reset, discard, amend, or push was performed.
- The prior release-validation commits are present:
  - `f47a915 docs: publish v1 release report`
  - `bb57dd8 fix(voice): enforce integrity pins`
  - `1ccc427 docs: add v1 validation plan`
- The latest recorded automated baseline is 958 daemon tests and 75 desktop tests, 1,033 total, with Python, TypeScript, Vite, Rust, and migration gates green. This baseline is historical until rerun after any fix.

## Required components and actual startup state

| Component | How it is started or selected | Starting observation |
|---|---|---|
| FastAPI daemon | `uv run --project apps/daemon python -m omnimac_daemon.main` | Running on `127.0.0.1:7710`; `/api/health` returned daemon `ok`, database `ok`. |
| Desktop frontend | Vite through the Tauri dev command | Running on `http://localhost:5188` because 5173/5174 are occupied by unrelated local processes. |
| Native desktop | `VITE_OmniMac_TOKEN=... pnpm -C apps/desktop tauri dev --config ...` | Native `target/debug/omnimac-desktop` started and the OmniMac window was observed using Codex computer interaction. |
| Local planner | Ollama on loopback, configured model `qwen3:4b` | Ollama is running locally. Runtime snapshot reported the planner unloaded until needed. No cloud fallback is configured. |
| Whisper runtime | `OmniMac_WHISPER_EXECUTABLE` | Local official whisper.cpp v1.8.6 binary exists at `data/runtime/whisper.cpp-v1.8.6/build/bin/whisper-cli`; the configured binary integrity pin was previously verified. |
| Whisper model | `OmniMac_WHISPER_MODEL_PATH` and `OmniMac_WHISPER_MODEL_SHA256` | `ggml-base.en.bin` is selected. `/api/runtime` reported `idle_cached` and integrity verified. |
| Local TTS | macOS local speech provider | Implemented and registered. Runtime snapshot reported unloaded until needed; readiness must be exercised in the real flow. |
| AX helper | Existing native helper, when running | Not required to establish microphone capture. Accessibility permission was previously denied and must not block voice-only testing. |

The runtime model files available for controlled comparison are:

| Model | Path | Recorded SHA-256 |
|---|---|---|
| tiny.en | `data/models/whisper/ggml-tiny.en.bin` | `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f` |
| base.en | `data/models/whisper/ggml-base.en.bin` | `a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002` |
| small.en | `data/models/whisper/ggml-small.en.bin` | `c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d` |

Model changes require restarting the daemon with the matching model path and integrity pin. Each model will be tested with the same ten user-spoken commands. The production default will change only if the measured result clearly beats the current base model under the required priority: Stop accuracy, intent accuracy, routing accuracy, latency, memory, then word accuracy.

## Voice activation and observability

- The native application registers global `Option+Space` through `tauri-plugin-global-shortcut` in `apps/desktop/src-tauri/src/lib.rs`.
- The command-center microphone button emits the same pressed/released events.
- `VoiceOverlay.tsx` requests `navigator.mediaDevices.getUserMedia({ audio: true })` and records mono signed 16-bit PCM locally. The daemon validates the declared rate/channels, wraps the bounded bytes in a private temporary WAV, and invokes the integrity-pinned local Whisper runtime. Partial recognition is throttled to avoid launching Whisper for every audio callback; final recognition always uses the complete capture.
- The microphone indicator is active only while the overlay state is `listening`.
- Daemon voice/runtime state and aggregate stage latency are available from authenticated `/api/runtime` and voice-session endpoints.
- Route selection is observable through `/api/intent/route` and the overlay route label.
- Task execution and verification are observable through the task API, WebSocket events, Execution HUD, operational presentation, and audit events.
- whisper.cpp creates a bounded temporary input file for each transcription and deletes it in a `finally` path. The real run will check that no temporary audio remains after each command.

## Recovered integration defects

The initial loopback CORS blocker is resolved. During recovery, the following additional defects were reproduced, repaired, and covered by regression tests:

1. Loopback/Tauri CORS preflight now succeeds while bearer authentication remains mandatory for protected requests.
2. Browser development mode can read the local session token safely; token reads are single-flight and do not create an unbounded retry loop.
3. Intentional WebSocket closure no longer changes the desktop to a false disconnected state, and the daemon observes client disconnects without hanging shutdown on an idle event queue.
4. Push-to-talk release during asynchronous startup is retained, a minimum capture window is enforced, pending PCM is flushed before stop, and cancellation cannot trigger finalisation.
5. Chromium/WebKit `MediaRecorder` output was incompatible with the pinned `whisper-cli`, which accepts WAV/FLAC/MP3/OGG rather than WebM/Opus. Capture now uses local PCM and the daemon constructs a bounded private WAV.
6. Typed and voice commands now share one authoritative deterministic dispatcher. Stop, speech interruption, status, supported app launch/focus, and installed skills do not enter the local planner.
7. Planner validation failures settle as terminal tasks and user-facing persona text no longer exposes Pydantic internals.
8. Deterministic no-task controls return valid persona responses instead of HTTP 409 failures. “Stop speaking” does not immediately start another utterance.
9. The first real microphone attempt proved that local PCM reached Whisper and produced partial transcripts, but it was not counted as a pass: pointer release could be lost outside the button, recognition was requested too early, and queued audio continued after cancellation. Pointer capture plus a global release listener now bounds capture to 30 seconds, batches uploads, delays the first partial, and prevents post-cancel uploads.
10. A typed `run the tests` preflight exposed a hollow-success route: the local planner listed applications and the task was marked complete without running tests. Natural project operations now resolve to authoritative installed skills; `run the tests` produces an exact `shell_run make test` step with R2 approval and exit-code verification.
11. A stale untrusted database workspace could override an explicitly configured trusted workspace. Startup now reconciles exact normalized paths from trusted launch configuration, preserves unrelated records, and selects the configured profile as the default.
12. Reconnecting desktop clients could miss task events and falsely show `No task running`. WebSocket connection is now considered established only after the authenticated server acknowledgement, and every authenticated reconnect refreshes tasks and pending approvals before presenting state.
13. The legacy `/api/voice/task` endpoint bypassed the deterministic command dispatcher. It now uses the same dispatcher as typed commands and push-to-talk sessions, so Stop, app, skill, and safety reflexes cannot fall through to the planner.
14. Exact approval language could still reach the planner as a new voice or text task. It now returns a deterministic clarification directing the user to the visible invocation-bound approval control; it never consumes a pending approval and makes zero model calls.
15. A failed authoritative app-focus plan could enter model-generated recovery. The model then changed the valid `app` argument into invalid `app_name`, reproducing the raw Pydantic failure shown in the desktop. Pre-built reflex and skill plans now permit bounded same-step retries but never model replacement.
16. The command endpoint treated its three-second settlement window as an exception and returned HTTP 500 while a legitimate task continued. Settlement now returns the current authoritative task snapshot at the timeout; WebSocket/task refresh carries later progress.
17. App launch/focus success was accepted before the required final focus was independently observed. App tools now wait for the native foreground postcondition and re-probe it independently; the orchestrator converts a failed focus postcondition into tool failure and preserves the original focus baseline across retries.
18. Voice transcript sessions could remain in memory if dispatch raised. Final submission now removes the single-use session in a `finally` path on every outcome.
19. Live `show me the modified files` missed a natural skill alias, entered the local planner, and stored the validator's raw Pydantic detail in task state. The phrase now resolves to the authoritative `project-health-check` skill, and `PlanRejected` serializes only its closed rejection code while retaining typed detail in-process.
20. Failed tasks could still expose internal recovery text in the desktop even after the planner exception itself was contained. Task presentation now supplies a bounded deterministic failure response, and Command Center/Execution HUD prefer that authoritative presentation over raw internal errors.
21. The voice overlay labelled every reflex-tier route as `Reflex`, including installed skills and clarification. Route labels now distinguish `Skill`, `Clarification`, `Reflex`, and `Local planner` from the authoritative intent result.
22. Explicit cancellation and global Stop zeroed audio but left cancelled session objects addressable. Cancellation now discards the session immediately, daemon shutdown clears active capture state, and a two-minute local janitor zeroes and removes abandoned unsubmitted sessions after UI loss. Opt-in transcript retention applies only to submitted transcript state, never cancelled audio.
23. Integration tests created SQLite engines without owning their teardown, causing nondeterministic aiosqlite worker-thread warnings after event-loop closure. The test harness now tracks and disposes every per-test engine before loop teardown; the full suite passes with unhandled thread warnings promoted to errors.

Live recovery evidence on 2026-07-14:

- `/api/health` returned daemon `ok` and database `ok`.
- The local runtime snapshot reported the Whisper binary/model integrity pin verified and no cloud fallback.
- The Chrome development UI showed `CONNECTED`.
- A typed `omnimac stop` traversed `/api/commands`, returned HTTP 200, created no task, and visibly displayed `Stopped. No external action was taken.` without model use.
- The first real microphone attempt delivered PCM to the daemon and local Whisper returned partial recognition. Because the release/cancellation defect interrupted finalisation, it is recorded as an unsuccessful diagnostic attempt, not a passed command.
- A live typed `Omnimac, run the tests.` command now stops at `WAITING_FOR_APPROVAL` with an exact R2 `shell_run make test` invocation and an exit-code verifier. No approval was bypassed.
- Live `omnimac stop`, `check the daemon`, and `start the backend` commands all returned deterministic no-task controls. Live `approve it` returned clarification and created no task.
- Finder, TextEdit, and Visual Studio Code application grants were created through the authenticated permissions API from the user's explicit authorization. They are persistent, scoped records; no profile expanded itself from model output.
- A real TextEdit launch attempt demonstrated that this Codex-hosted test process can delay macOS foreground transitions while terminal automation is active. OmniMac therefore ended `FAILED_REQUIRES_USER`; it did not claim completion. A separate native AppKit probe could focus TextEdit once the controlling call yielded. This is recorded as an environment-limited focus capstone, not a pass.
- Live `show me the modified files` completed the authoritative three-step read-only skill (`git_status`, `git_log`, `fs_list_dir`) with no model call. A deliberately novel repository-status request produced `planning failed: bad_arguments` plus the safe persona response; neither task nor display payload contained Pydantic internals.
- The final combined automated gate passed: 996 daemon tests and 95 desktop tests (1,091 total), with one locked-screen focus test skipped. Ruff, Ruff formatting, strict mypy, ESLint, TypeScript, Vite build, Rust check/test, and Alembic upgrade also passed. A strict daemon rerun promoted unhandled worker-thread warnings to errors and remained green.
- Local macOS TTS playback and interruption were exercised successfully through authenticated voice endpoints. The runtime remained local-only.
- After restarting the real daemon on the repaired build, `/api/health` was healthy, runtime status was offline/local with the Whisper model integrity verified, typed Stop was model-free with no task creation, and a live voice session returned one cancellation snapshot followed by 404. The route API classified Stop, installed-skill execution, approval clarification, and app-open reflexes without model use.
- The final live integrity check verified all 11 recent persisted task audit chains and found no `omnimac-voice-*` temporary audio file in the system temporary directory.
- The packaged exact Accessibility helper was running, but a fresh authenticated probe still reported `not_determined`. The host later locked and the foreground probe reported `com.apple.loginwindow`; these are recorded as blocked environment evidence, not product passes.
- A current visible desktop re-check could not run because macOS was locked and automatic unlock is intentionally prohibited. The previous unlocked browser UI evidence remains valid for the contained-failure and Accessibility displays, but no new post-restart UI pass is claimed.
- A clean post-fix real microphone command remains pending. It will not be inferred from automated PCM tests, partial recognition, or typed commands.

## Exact continuation plan

1. Ask the user to hold push-to-talk and personally speak `Omnimac, stop.`; collect the real partial/final transcript, route, control result, latency, and temporary-file evidence.
2. With `base.en`, ask the user to speak the remaining four required smoke commands one at a time. For each command collect partial/final text, correction, route, task/result verification, persona display/spoken result, stage latency, and temporary-audio deletion evidence.
3. If all five commands enter the real task pipeline, compare tiny.en, base.en, and small.en with the same ten user-spoken commands per model.
4. Run the remaining real-user command matrix to at least 30 total microphone commands, including safety/ambiguity and operational follow-ups.
5. Run five real acoustic Stop trials, three real barge-in trials, the voice-approval safety gate, and an offline-localhost-only voice-to-action trial.
6. Fix only defects exposed by those real tests, always with a failing regression test first, and rerun the exposing real command.
7. Update `docs/VOICE_MODEL_EVALUATION.md` and `docs/V1_VOICE_COMMAND_MATRIX.md`, then write `docs/REAL_VOICE_TEST_REPORT.md` with only measured results and the required status vocabulary.

## User participation required

The user must personally speak every command used as real microphone evidence. Codex may operate push-to-talk, inspect transcripts, edit only when the test calls for correction, monitor execution, and verify visible results. The following actions cannot be completed autonomously:

- granting macOS microphone permission in System Settings;
- speaking the five smoke commands;
- speaking each model-comparison and command-matrix utterance;
- speaking each acoustic Stop and barge-in command.

Generated audio, prerecorded synthetic audio, bundled samples, and typed transcripts will not be counted as real microphone results.

## Starting claim ceiling

At the current checkpoint, local voice transport into Whisper, authoritative routing, reconnect reconciliation, and all automated gates are verified. Real microphone-to-action readiness remains unverified until the user personally completes a post-fix spoken command. No real voice pass is claimed yet.

## Current manual retry

With the daemon and desktop running, hold the microphone button for two to three seconds, say `Omnimac, stop.`, release, and wait up to five seconds. The pass requires a visible final transcript, a `reflex / stop` route, `Stopped. No external action was taken.`, no task creation, and no retained temporary audio. A partial transcript alone is not a pass.
