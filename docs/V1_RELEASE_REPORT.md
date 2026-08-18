# OmniMac v1 release report

## Release decision

```text
OmniMac v1.0 RELEASE CANDIDATE
```

Implementation and automated safety gates are green, but mandatory real voice,
Accessibility, distribution, and clean-install evidence is absent. The exact
blockers below prevent `OmniMac v1.0 VALIDATED`.

## Exact build and host

- Branch: `phase-5/persona`
- Validation base: `ceb1b3470279a7e6abb0051532d46fbba0464ea5`
- Validation commits: `1ccc427`, `bb57dd8` plus this report commit
- Hardware: Apple M4, arm64, 16 GiB unified memory
- macOS: 26.3, build 25D125
- Desktop artifact: OmniMac 0.1.0 / `dev.omnimac.desktop`
- AX helper: `me.adityalabs.omnimac.axhelper`

## Local runtime and models

whisper.cpp v1.8.6 was built from verified upstream commit
`23ee03506a91ac3d3f0071b40e66a430eebdfa1d`, Release, Metal on, Core ML off.
Binary SHA-256:
`472df5652fae98387e9466733063f101a5b461ebeeb1bf69508abce813139c69`.

| Candidate | Bytes | SHA-256 | Real microphone result |
|---|---:|---|---|
| tiny.en | 77,704,715 | `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f` | Not run |
| base.en | 147,964,211 | `a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002` | Not run |
| small.en | 487,614,201 | `c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d` | Not run |

All pins validate in the local registry. A release-blocking integrity gap was
fixed: configured runtime/model SHA-256 mismatches now fail typed-unavailable
before transcription and runtime status reports verified pins. Base.en is the
current validation configuration, not a production selection.

## Voice result

All three models transcribed whisper.cpp's bundled JFK WAV locally. The real
managed base.en sample produced first partial 743 ms and finalization 644 ms,
supported edit/cancel, and left no `omnimac-voice-*` temp file. This is bundled
sample evidence only. Zero real microphone commands and zero acoustic Stop
trials were completed, so WER, intent/routing accuracy, workflow completion,
real Stop, and acoustic barge-in remain unmeasured. Automated voice approval,
Stop, retention, crash, and offline boundaries pass.

## Accessibility result

The final exact helper executable SHA-256 is
`ae0908575ab2ad2d88cdfb91f3879ded90f0ae7f221a0961863810f5dbb8054b`.
It ran as the packaged background app with a current-user mode-0600 socket and
parent PID 1. OmniMac opened the Settings pane only through an explicit requested
API action; the user did not grant trust during the run. Fresh state is
`denied`, so fixture mutation, delayed/ambiguous/moving/modal capstones,
TextEdit exact read-back, and real revocation were not run. Existing VS Code
workspace association/focus evidence remains valid, but no AX capability was
promoted.

## Offline, resource, signing, and install result

- Offline external-browser denial and local-only architecture pass automated
  tests; complete real microphone-to-action offline operation was not run.
- Partial resource measurements are in `V1_RESOURCE_REPORT.md`; installed
  workflow, battery, thermal, and sustained concurrency remain open.
- Zero Developer ID identities exist. The rebuilt 217 MB app and 196 MB DMG are
  ad-hoc signed; deep strict code-sign verification now passes, but Gatekeeper
  rejects the app and no notarization ticket exists.
- The DMG now contains the frozen daemon, exact helper, whisper.cpp executable,
  base.en model, and SHA-256/size manifest. The app live-started and
  authenticated its own daemon/helper without repository services. Normal Quit
  and forced desktop termination both cleaned up children. Clean-account
  installation and all 20 first-run/upgrade/uninstall checks remain unrun.
- A second packaged-app launch fails closed before replacing the running
  helper or daemon; the original authenticated runtime remains healthy.
- Ollama/Qwen and the Playwright Chromium payload remain explicit host
  prerequisites rather than silently downloaded or cloud-backed dependencies.

## Security and automated gates

No new high-severity automated security failure was found. Integrity mismatch,
voice approval/replay boundary, scope/risk authority, Stop cancellation,
retention, network isolation, AX profile/permission boundaries, redaction, and
audit-chain tests pass. Real acoustic feedback/background-audio attacks,
TCC revocation, installed-helper impersonation, and offline packet evidence
remain manual blockers.

| Gate | Result |
|---|---|
| Daemon | 999 passed, no skip |
| Desktop | 97 passed across 14 files |
| Aggregate daemon + desktop | 1,096 passed, no skip |
| Ruff / format | clean / 225 files |
| Strict mypy | clean, 120 source files |
| ESLint / TypeScript / Vite | clean / clean / built |
| Cargo / Rust | check passed / 8 tests passed |
| Swift helper | release build/package passed |
| Alembic | fresh DB upgraded through `0004_hash_chain` |
| App / DMG | built, manifest matched, strict ad-hoc signature passed |

The native app and mounted DMG now include
`NSMicrophoneUsageDescription`: OmniMac records only while push-to-talk is active
and transcribes locally. This repairs the packaging reason Chrome could receive
audio while the native bundle could not request its own permission. It is not a
substitute for the remaining real 30-command microphone evidence.

The final operator check also proved scope refusal: `Open TextEdit` proposed the
authoritative app tool but executed nothing because TextEdit was not granted in
the workspace. The desktop now exposes an explicit audited grant form for app,
path, and domain scope; validation did not auto-grant TextEdit.

## Mandatory blockers

1. No 30-command real microphone corpus or production STT selection.
2. No ten-trial acoustic Stop or real barge-in/echo result.
3. No complete offline real voice-to-action workflow.
4. Accessibility trust is denied for the exact helper; real AX capstones and
   revocation remain unrun.
5. No Developer ID, notarization, staple, or Gatekeeper-accepted app.
6. The package still lacks Ollama/Qwen and Playwright Chromium onboarding and
   has no clean-account validation.
7. Installed-build resource, daily-workflow, upgrade, and uninstall evidence is
   absent.

## Exact capability claim

OmniMac is a local-first release candidate with a deterministic safety core,
verified local planning, a packaged integrity-pinned daemon/speech/helper core, and
automated coverage for voice, focus, Accessibility boundaries, approvals,
verification, recovery, and audit. Real broad speech accuracy, TCC-backed UI
control, notarized distribution, and clean installation are not yet validated.
