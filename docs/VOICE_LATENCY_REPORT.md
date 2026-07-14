# Voice latency report

**Measured:** 2026-07-14 on Apple M4 / 16 GB, current development build

`python -m thoth_daemon.evals.run_voice_latency` measured deterministic local
code paths. These are component timings, not end-to-end microphone or global
shortcut timings.

| Stage | Samples | p50 | p95 | Target | Result |
|---|---:|---:|---:|---:|---|
| In-memory recording-state start | 1,000 | 0.005 ms | 0.005 ms | <200 ms | pass, component only |
| Reflex route | 10,000 | 0.001 ms | 0.001 ms | <100 ms | pass |
| Known-skill route | 10,000 | 0.002 ms | 0.002 ms | <250 ms | pass |
| TTS process interruption | 25 | 0.364 ms | 0.426 ms | <200 ms | pass, injected local process |
| Stop authority acknowledgement | 500 | 0.043 ms | 0.047 ms | <250 ms | pass, idle collaborators |
| First Whisper partial | — | — | — | <700 ms | unavailable: no model/runtime |
| Whisper finalisation | — | — | — | <1.5 s | unavailable: no model/runtime |
| Local planning visible | — | — | — | <500 ms | not instrumented end-to-end |

The daemon also retains rolling numeric-only p50/p95 samples (maximum 256 per
stage) for real sessions and exposes them under `/api/runtime`. Metrics reset on
restart and contain no audio or transcript content.
