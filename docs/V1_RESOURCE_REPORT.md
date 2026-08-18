# OmniMac v1 resource report

**Host:** Apple M4, 16 GiB unified memory, macOS 26.3 (25D125)  
**Date:** 2026-07-14  
**Status:** partial development-host measurements; installed-build workflow pending

## Measured

| Measurement | Result | Evidence ceiling |
|---|---:|---|
| Daemon idle RSS | about 11 MiB | development process |
| Native desktop idle RSS | about 38 MiB before workload | development process |
| AX helper idle RSS | about 6 MiB | exact packaged helper |
| Qwen3 4B loaded | 3.2 GB reported by Ollama; llama-server RSS about 3.0 GB | real local model, 100% GPU reported |
| Qwen cold request | 3.52 s total; 2.18 s load | one constrained probe, not a distribution |
| tiny.en sample max RSS | 244 MB cold / 234 MB warm | bundled JFK WAV only |
| base.en sample max RSS | 349 MB cold / 349 MB warm | bundled JFK WAV only |
| small.en sample max RSS | 823 MB cold / 848 MB warm | bundled JFK WAV only |
| Base sample with Qwen loaded | 8.58 s API round trip | real concurrent local runtimes; one sample |
| Battery state | 74%, discharging during probe | observation only |
| Thermal state | no warning recorded | `pmset -g therm`; not a sustained test |

The runtime manager reports a 12 GiB ceiling and serializes heavy Qwen/Whisper
use in managed voice sessions. Reflex remains available while models are
unloaded. Automated crash-restart, idle eviction, battery-saver eviction, and
memory-pressure tests pass.

## Not measured

Installed-build idle/peak memory, real microphone capture, full voice-to-action
peak, sustained CPU/GPU utilization, battery drain, thermal behavior, real
Qwen/Whisper overlap under repeated commands, and installed-build model crash
recovery were not measured. `powermetrics` was not used because this run does
not use `sudo`. These remain release blockers, not inferred passes.

