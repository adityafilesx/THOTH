# Voice latency report

**Measured:** 2026-07-14 on Apple M4 / 16 GiB

| Stage | Samples | p50 | p95 | Result/evidence ceiling |
|---|---:|---:|---:|---|
| In-memory recording start | 1,000 | 0.005 ms | 0.005 ms | component pass |
| Reflex route | 10,000 | 0.001 ms | 0.001 ms | component pass |
| Known-skill route | 10,000 | 0.002 ms | 0.002 ms | component pass |
| TTS process interruption | 25 | 0.384 ms | 0.841 ms | injected local process pass |
| Stop acknowledgement | 500 | 0.042 ms | 0.048 ms | idle collaborators pass |
| Base.en first partial | 1 | 742.96 ms | 742.96 ms | bundled WAV; exceeds 700 ms target |
| Base.en finalization | 1 | 644.23 ms | 644.23 ms | bundled WAV; below 1.5 s target |
| Base.en with Qwen resident | 1 | 8.58 s | 8.58 s | one concurrent sample; fail for interactive use |

The first five measurements come from the deterministic component benchmark.
The Whisper rows came from the real pinned runtime through daemon APIs, but the
input was the bundled JFK WAV rather than a microphone. Real global-shortcut,
capture/VAD, acoustic barge-in, 30-command, cold/warm p50/p95, and installed
build latency remain unmeasured. Numeric runtime metrics contain no audio or
transcript and reset on restart.
