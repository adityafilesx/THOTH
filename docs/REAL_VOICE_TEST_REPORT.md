# THOTH real voice test report

**Date:** 2026-07-14
**Status:** automated pipeline pass; real microphone release gate pending

## Result

THOTH's local voice implementation, deterministic command routing, safety boundaries, task lifecycle, desktop integration, and build gates are green in automation. The first real microphone attempt reached local Whisper and produced partial text, but exposed capture-release defects and did not produce a valid final submission. Those defects are fixed and regression-tested; no post-fix user-spoken command has yet been completed, so real voice readiness is not claimed.

## Verified in this run

- Daemon health and database health are live on loopback.
- Qwen3 4B planning is configured through the loopback-only local provider with no cloud fallback.
- whisper.cpp and `ggml-base.en.bin` integrity pins verify before recognition.
- macOS local TTS playback and interruption work through the real endpoints.
- Typed `thoth stop` is model-free, creates no task, and returns the restrained persona response.
- Exact voice/text approval language cannot approve or enter the planner.
- `run the tests` resolves to the installed authoritative skill and stops at exact R2 approval.
- Failed app focus cannot be reported as completed.
- Temporary transcript sessions are single-use and removed on success or exception.
- 993 daemon tests and 91 desktop tests pass. Python lint/format/typecheck, ESLint, TypeScript, Vite production build, Rust check, and Alembic migration pass.

## Not yet verified

- A clean post-fix command spoken by the user through the real microphone.
- The five-command real microphone smoke set.
- The three-model ten-command comparison.
- The 30-command real microphone matrix.
- Five acoustic Stop repetitions and three barge-in repetitions.
- Distribution signing, notarization, and clean-install TCC behavior.

## Required next evidence

The user must hold push-to-talk, say `Thoth, stop.`, release, and wait for final recognition. A pass requires the final transcript, deterministic Stop route, no task creation, local response, bounded latency, and deletion of temporary audio. Synthetic, prerecorded, typed, or partial recognition is not counted.

## Honest capability claim

The current build has a verified local safety and execution core with an automated local voice pipeline. Real microphone-to-action reliability remains a release-candidate gate until the user completes the post-fix spoken matrix.
