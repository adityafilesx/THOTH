# Local speech model evaluation

**Host:** Apple M4, 16 GiB unified memory, macOS 26.3
**Date:** 2026-07-14
**Selection status:** no production model selected; real microphone corpus pending

whisper.cpp v1.8.6 was built locally from verified commit
`23ee03506a91ac3d3f0071b40e66a430eebdfa1d` with Apple Clang 17, Release,
Metal enabled, and Core ML disabled. Runtime SHA-256 is
`472df5652fae98387e9466733063f101a5b461ebeeb1bf69508abce813139c69`.
No cloud STT or mock fallback was used.

| Model | Size | SHA-256 | Sample cold/warm | Sample max RSS | Sample text |
|---|---:|---|---:|---:|---|
| tiny.en | 77,704,715 B | `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f` | 7.77 / 0.57 s | 244 / 234 MB | correct after normalized punctuation |
| base.en | 147,964,211 B | `a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002` | 0.55 / 0.56 s | 349 / 349 MB | correct after normalized punctuation |
| small.en | 487,614,201 B | `c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d` | 1.08 / 1.07 s | 823 / 848 MB | correct after normalized punctuation |

The cold order is not a controlled model comparison: tiny.en paid the initial
Metal setup cost. These one-file results use whisper.cpp's bundled JFK WAV and
are health/resource probes only. They are not real microphone, noisy-room,
accent, command-routing, or WER release evidence.

A managed base.en session produced first partial 742.96 ms and finalization
644.23 ms, supported final/edit/cancel, and left no private temp audio. With
Qwen3 4B resident, the same one-shot base sample took 8.58 seconds, confirming
that concurrent heavy-runtime behavior needs the required real workload study.

The fixed 30-command real microphone matrix was not captured. Therefore
word-error rate, intent accuracy, routing accuracy, Stop accuracy, correction
rate, real partial/final p50/p95, utilization distribution, and production
model selection remain unavailable. Base.en is configured for validation only.
