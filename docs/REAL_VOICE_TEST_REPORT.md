# OmniMac real voice test report

**Date:** 2026-07-14
**Status:** PARTIALLY WORKING — automated and live API pipeline pass; real microphone release gate pending

## Result

OmniMac's local voice implementation, deterministic command routing, safety boundaries, task lifecycle, desktop integration, and build gates are green in automation. The first real microphone attempt reached local Whisper and produced partial text, but exposed capture-release defects and did not produce a valid final submission. Those defects are fixed and regression-tested; no post-fix user-spoken command has yet been completed, so real voice readiness is not claimed.

## Verified in this run

- Daemon health and database health are live on loopback.
- Qwen3 4B planning is configured through the loopback-only local provider with no cloud fallback.
- whisper.cpp and `ggml-base.en.bin` integrity pins verify before recognition.
- macOS local TTS playback and interruption work through the real endpoints.
- Typed `omnimac stop` is model-free, creates no task, and returns the restrained persona response.
- Exact voice/text approval language cannot approve or enter the planner.
- `run the tests` resolves to the installed authoritative skill and stops at exact R2 approval.
- Failed app focus cannot be reported as completed.
- Temporary transcript sessions are single-use and removed on success, exception, explicit cancel, or bounded abandonment expiry. Active capture is cleared on daemon shutdown.
- 996 daemon tests and 95 desktop tests pass (1,091 total), with one locked-screen focus test skipped. Python lint/format/typecheck, ESLint, TypeScript, Vite production build, Rust check/test, and Alembic migration pass. The daemon suite also passes with worker-thread warnings treated as errors.
- The repaired daemon is currently running on loopback. Live typed Stop is model-free, live route classification distinguishes skill/clarification/reflex/planner, and cancelled voice sessions become inaccessible immediately.
- All 11 recent persisted task audit chains verified, and the final temporary-directory check found no retained OmniMac voice audio.

## Not yet verified

- A clean post-fix command spoken by the user through the real microphone.
- The five-command real microphone smoke set.
- The three-model ten-command comparison.
- The 30-command real microphone matrix.
- Five acoustic Stop repetitions and three barge-in repetitions.
- Distribution signing, notarization, and clean-install TCC behavior.
- A current post-restart desktop visual pass; the Mac locked before Computer Use could inspect it.

## Readiness snapshot

These percentages are engineering completion estimates, not measured accuracy scores:

| Area | Status | Estimate | Evidence ceiling |
|---|---|---:|---|
| Deterministic safety/execution core | WORKING | 96% | Full automated gate, live command/Stop, approval and verification controls |
| Desktop command experience | WORKING | 88% | 95 tests and prior unlocked live UI; current post-restart check blocked by lock |
| Local voice implementation | PARTIALLY WORKING | 72% | Local PCM/STT/TTS/session pipeline is green; no clean post-fix user-spoken pass |
| Real microphone readiness | IMPLEMENTED BUT UNVERIFIED | 35% | Zero completed post-fix human microphone commands |
| Semantic Accessibility control | IMPLEMENTED BUT UNVERIFIED | 55% | Helper/profile/tool automation is green; exact helper TCC is `not_determined` |
| Distribution packaging | BLOCKED | 25% | No Developer ID/notarization/clean-install evidence |
| Validated v1 product | PARTIALLY WORKING | 60% | Strong local core, but human voice, TCC, and distribution gates remain open |

Wake word, proactive behavior, universal application control, and long-term personal memory are NOT IMPLEMENTED and are not part of the current release claim.

## Required next evidence

The user must hold push-to-talk, say `Omnimac, stop.`, release, and wait for final recognition. A pass requires the final transcript, deterministic Stop route, no task creation, local response, bounded latency, and deletion of temporary audio. Synthetic, prerecorded, typed, or partial recognition is not counted.

## Honest capability claim

The current build has a verified local safety and execution core with an automated local voice pipeline. Real microphone-to-action reliability remains a release-candidate gate until the user completes the post-fix spoken matrix.
