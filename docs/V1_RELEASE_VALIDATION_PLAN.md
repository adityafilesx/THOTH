# THOTH v1.0 release validation plan

**Audit date:** 2026-07-14  
**Branch:** `phase-5/persona`  
**Commit:** `ceb1b3470279a7e6abb0051532d46fbba0464ea5`

## Initial repository state

The tracked tree was clean at audit time. The existing untracked `.agents/`
and `.codex/` directories are preserved and are outside this validation run.
There were no staged changes and no stashes. No remote push is authorized.

The implementation baseline is the Phase 5.4/5.5 release-candidate code. The
last recorded complete automated gate is 956 standalone daemon tests, 75
desktop tests, and 1,030 aggregate passing tests, with one transient
locked-desktop focus skip that passed on an independent unlocked rerun. Ruff,
strict mypy, ESLint, TypeScript, Vite, Cargo, Swift helper packaging/signature,
and Alembic through `0004_hash_chain` were green. These are prior recorded
results until the final gate is rerun during this validation.

## Audited host

| Property | Observed value |
|---|---|
| Hardware | Apple M4, arm64 |
| Unified memory | 16 GiB (`17179869184` bytes) |
| macOS | 26.3, build 25D125 |
| Python toolchain | uv 0.11.28, repository Python 3.12 |
| Node / pnpm | Node 20.20.2 / pnpm 10.12.1 |
| Rust | rustc 1.96.1 / cargo 1.96.1 |
| Swift | Apple Swift 6.2.1 |
| Ollama | 0.31.1, loopback API responsive |
| Local planner models | qwen3:4b Q4_K_M, qwen3:8b Q4_K_M |
| Default audio input | Built-in MacBook Air Microphone, 44.1 kHz |
| Microphone permission | Not yet exercised or established as release evidence |

The daemon, native Tauri desktop, Vite development server, and AX helper were
already running from the preceding validation session. Their continued
operation is development evidence only, not clean-install evidence.

## Local speech runtime and models

No `whisper-cli`, CMake, Ninja, ffmpeg, or sox executable was present. No
Whisper GGML model was found in the repository data directory, THOTH
Application Support, user cache/share directories, or Homebrew shared data.
Consequently no production STT model is selected and no real WER, intent,
routing, Stop, partial/final latency, memory, or concurrent-Qwen measurement
exists yet.

The validation will prefer a repository-local or user-local whisper.cpp build
at a stable path. It will record the upstream commit/version, build options,
binary SHA-256, health/version probes, and cancellation behavior. The
`tiny.en`, `base.en`, and (memory permitting) `small.en` GGML candidates will
be stored outside Git under the existing local-model data hierarchy with file
size, SHA-256, source, license, quantization, and expected memory metadata.
Integrity mismatch must prevent use.

## Accessibility host and trust

| Property | Observed value |
|---|---|
| Helper path | `apps/ax-helper/dist/THOTH Accessibility Helper.app` |
| Bundle identifier | `me.adityalabs.thoth.axhelper` |
| Executable | `THOTHAXHelper` |
| Executable SHA-256 | `ae0908575ab2ad2d88cdfb91f3879ded90f0ae7f221a0961863810f5dbb8054b` |
| Signature | valid ad-hoc hardened-runtime signature; no TeamIdentifier |
| Gatekeeper | rejected as an unnotarized/ad-hoc artifact |
| Socket | `~/Library/Application Support/THOTH/ax-helper.sock` |
| Socket mode / owner | `srw-------`, current user `aditya1981:staff` |
| Process | running as the exact packaged helper, parent PID 1 |
| AX trust | `not_determined` / helper reports untrusted |

THOTH will not automate permission granting or modify TCC. The user must
manually grant Accessibility access to this exact bundle. Only a fresh helper
probe returning `AXIsProcessTrusted() == true` can begin real AX capstones.

## Signing and packaging state

`security find-identity -v -p codesigning` reported zero valid signing
identities. Developer ID signing, notarization, stapling, and Gatekeeper
release acceptance are therefore blocked by credentials on this host. The
ad-hoc helper remains usable for local validation but is not production
release evidence. Clean-machine/account validation is also not established;
the developer checkout cannot substitute for it.

## Validation sequence

1. Build and integrity-pin a local whisper.cpp runtime without `sudo` or a
   global install; probe version, health, Metal support, and cancellation.
2. Acquire and hash tiny.en, base.en, and small.en from the authoritative
   whisper.cpp model source; record immutable local metadata.
3. Prepare a fixed 30-command corpus and microphone-capture worksheet without
   fabricating recordings. Run each candidate against real user recordings,
   then select by safety/intent correctness first and latency/memory second.
4. Validate the visible push-to-talk lifecycle, transcript edit/submit-once,
   privacy cleanup, microphone denial, app termination, and global shortcut.
5. Run ten real acoustic Stop trials and real TTS barge-in trials across task
   states. Verify cancellation and approval invalidation independently.
6. Prove spoken/replayed approval cannot consume R2/R3 approval and that a
   spoken denial constrains or cancels the task.
7. Run the 30-command matrix and calculate intent, routing, workflow, latency,
   memory, and failure results from captured evidence.
8. Enable network isolation and prove a complete local voice-to-action flow
   plus deterministic refusal of a network-dependent request, with connection
   evidence where practical.
9. After manual TCC grant, verify exact helper trust and run fixture, delayed,
   ambiguity, moving-element, modal, TextEdit, VS Code, and manual-revocation
   AX capstones on an unlocked desktop.
10. Build the Tauri distribution artifact. Sign/notarize only if credentials
    become available; otherwise record the precise credential blocker.
11. Validate first-run, upgrade, relaunch, login behavior, uninstall, data
    removal, and orphan-process cleanup in a clean macOS account or equivalent
    isolated environment.
12. Measure idle/full-workflow resource use and model crash recovery on the
    target M4/16 GiB host.
13. Run the adversarial matrix, all automated gates, audit-chain validation,
    and publish the release report with exactly one release decision.

## Evidence required for `THOTH v1.0 VALIDATED`

- Integrity-pinned whisper.cpp runtime and candidate models.
- Production STT selection from real microphone measurements.
- At least 30 distinct real spoken commands with at least 90% intent and
  routing accuracy, at least 90% supported-workflow completion, 100% Stop,
  zero voice approvals, zero scope escape, and zero unapproved external effect.
- Real visible microphone lifecycle, transcript correction, retention cleanup,
  acoustic Stop/barge-in, and complete offline local voice-to-action evidence.
- Fresh trust for exact helper `me.adityalabs.thoth.axhelper`, independent AX
  read-back for every promoted capability, and fail-closed real revocation.
- Signed/notarized artifacts when credentials are available, plus a real
  clean-account/machine installation and uninstall pass.
- Resource/crash evidence, zero unresolved high-severity security findings,
  and a fully green final automated gate.

Until every mandatory item is evidenced, the only permitted decision is
`THOTH v1.0 RELEASE CANDIDATE` with each blocker stated explicitly.

## Current environment-dependent blockers

- Real microphone actions require the user to speak and respond to any macOS
  microphone permission prompt.
- Accessibility actions require the user to manually grant and later revoke
  TCC for the exact packaged helper.
- Developer ID/notarization requires credentials not present in the keychain.
- Clean-install evidence requires a clean macOS user/account or equivalent
  environment distinct from this developer checkout.
- A 30-command acoustic corpus, noisy-room variants, and physical distance
  variations require user participation and cannot be simulated or inferred.
