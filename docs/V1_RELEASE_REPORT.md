# THOTH v1 release report

## Release decision

```text
THOTH v1.0 RELEASE CANDIDATE
```

Implementation and automated safety gates are green, but mandatory real voice,
Accessibility, distribution, and clean-install evidence is absent. The exact
blockers below prevent `THOTH v1.0 VALIDATED`.

## Exact build and host

- Branch: `phase-5/persona`
- Validation base: `ceb1b3470279a7e6abb0051532d46fbba0464ea5`
- Validation commits: `1ccc427`, `bb57dd8` plus this report commit
- Hardware: Apple M4, arm64, 16 GiB unified memory
- macOS: 26.3, build 25D125
- Desktop artifact: THOTH 0.1.0 / `dev.thoth.desktop`
- AX helper: `me.adityalabs.thoth.axhelper`

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
supported edit/cancel, and left no `thoth-voice-*` temp file. This is bundled
sample evidence only. Zero real microphone commands and zero acoustic Stop
trials were completed, so WER, intent/routing accuracy, workflow completion,
real Stop, and acoustic barge-in remain unmeasured. Automated voice approval,
Stop, retention, crash, and offline boundaries pass.

## Accessibility result

The exact helper executable SHA-256 was
`552d626495f6b732ce67c06bd34b4a70bfb397370756805b4f71a0d907687371`.
It ran as the packaged background app with a current-user mode-0600 socket and
parent PID 1. THOTH opened the Settings pane only through an explicit requested
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
- Zero Developer ID identities exist. The app is ad-hoc, strict code-sign
  verification fails, Gatekeeper rejects it, and no notarization ticket exists.
- The DMG contains only the desktop shell. Clean installation and all 20
  first-run/upgrade/uninstall checks were not run.

## Security and automated gates

No new high-severity automated security failure was found. Integrity mismatch,
voice approval/replay boundary, scope/risk authority, Stop cancellation,
retention, network isolation, AX profile/permission boundaries, redaction, and
audit-chain tests pass. Real acoustic feedback/background-audio attacks,
TCC revocation, installed-helper impersonation, and offline packet evidence
remain manual blockers.

| Gate | Result |
|---|---|
| Daemon | 958 passed, 1 dependency warning, no skip |
| Desktop | 75 passed across 12 files |
| Aggregate `make test` | 1,033 passed, no skip |
| Ruff / format | clean / 219 files |
| Strict mypy | clean, 118 source files |
| ESLint / TypeScript / Vite | clean / clean / built |
| Cargo / Rust | check passed / 1 test passed |
| Swift helper | release build/package passed |
| Alembic | fresh DB upgraded through `0004_hash_chain` |

## Mandatory blockers

1. No 30-command real microphone corpus or production STT selection.
2. No ten-trial acoustic Stop or real barge-in/echo result.
3. No complete offline real voice-to-action workflow.
4. Accessibility trust is denied for the exact helper; real AX capstones and
   revocation remain unrun.
5. No Developer ID, notarization, staple, or Gatekeeper-accepted app.
6. The package omits daemon/helper/models/onboarding and is not clean-install
   capable; no clean-account validation exists.
7. Installed-build resource, daily-workflow, upgrade, and uninstall evidence is
   absent.

## Exact capability claim

THOTH is a local-first release candidate with a deterministic safety core,
verified local planning, an integrity-pinned local speech runtime, and
automated coverage for voice, focus, Accessibility boundaries, approvals,
verification, recovery, and audit. Real broad speech accuracy, TCC-backed UI
control, notarized distribution, and clean installation are not yet validated.

