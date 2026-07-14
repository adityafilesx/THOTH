# Local speech model evaluation

**Host:** Apple M4, 16 GB unified memory
**Date:** 2026-07-14
**Selection status:** pending real model availability

The primary provider is whisper.cpp and the configured candidate is
`ggml-base.en.bin`. No `whisper-cli`, whisper.cpp Homebrew package, local
Whisper model, `ffmpeg`, or `sox` was present in the audited environment.
Therefore tiny/base/small load time, word-error rate, partial/final latency,
peak memory, utilisation, and Qwen-concurrent behaviour were not measured.

No model was downloaded automatically, no cloud STT was used, and the mock
provider was not substituted as live evidence. Missing executable/model state
returns typed unavailable/HTTP 503 and audio remains private/deleted.

Before daily-driver testing, install local whisper.cpp and tiny/base/small
candidates, verify their hashes, run the same 30-command corpus at least three
times per candidate on the M4/16 GB host, measure WER and p50/p95 latency plus
peak memory with Qwen3 4B loaded, then select by correctness first and latency
within the serialized heavy-workload memory budget. Until then no speech
accuracy or selected-model claim is made.
