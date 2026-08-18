# Phase 5.4 capstone evidence

**Date:** 2026-07-14  
**Branch:** `phase-5/persona`  
**Host:** Apple M4 Mac, macOS, real NSWorkspace/ApplicationServices context

## Evidence ceiling

The semantic AX implementation, application fixture, safety boundaries, and
desktop diagnostics are built and automated tests pass. Phase 5.4 is **not
claimed complete** because the exact helper does not have macOS Accessibility
trust. During v1 validation OmniMac opened System Settings only through the
explicit requested endpoint; the fresh state became `denied`. No TCC control
was automated and no real AX mutation ran.

No AX capability was promoted from experimental to verified on the strength of
unit or mock evidence.

## Real host evidence

| Probe | Outcome | Evidence |
|---|---|---|
| Package native fixture | Pass | Release Swift build completed; ad-hoc signature passed `codesign --verify --deep --strict`. |
| Unique fixture identity | Pass | Packaged plist and real running application both reported `me.adityalabs.omnimac.axtest`; PID 57350 during the run. |
| Current AX permission | Fail closed | `AXIsProcessTrusted()` returned false. After an explicit Settings visit, typed status is `denied`; no permission control was automated. |
| Real foreground capture | Pass, locked state | NSWorkspace returned `loginwindow` / `com.apple.loginwindow`, and the foreground broker reported that real state. |
| Supported app inventory | Pass | Finder, TextEdit, and Code were observed as real running applications. |
| VS Code workspace association | Pass | Running `com.microsoft.VSCode` plus the authoritative approved OmniMac path/task workspace matched; title evidence remained a hint. |
| Current focus restoration rerun | Environment skip | `test_focus_live.py` skipped because loginwindow was frontmost. The earlier unlocked 2026-07-14 Code → TextEdit → Code run remains valid real evidence: final bundle `com.microsoft.VSCode`, `restored=True`, `verified=True` (see `PHASE_5_2_5_3_CAPSTONE.md`). |
| Permission-free real AX inspection | Blocked | Profile remains experimental and TCC is absent. No adapter snapshot or action occurred. |

The focused live command produced **16 passed, 1 skipped** across foreground,
focus, workspace, and legacy real-AX fail-closed tests. A verbose
foreground/workspace rerun produced **5 passed**. The Phase 5.4 targeted
automated matrix produced **176 passed**.

## Capstone matrix

| Capstone | Outcome | Verification / limitation |
|---|---|---|
| A — Focus restoration | Pass from unlocked handoff evidence; current rerun skipped | Exact final bundle was independently verified on the unlocked run. Current loginwindow state prevents a second interactive transition. |
| B — Test-app form | Not verified | TCC is `not_determined`; no field, toggle, picker, Save, or status action ran. Mock/unit verification is not real evidence. |
| C — Delayed element | Not verified | Bounded semantic wait is implemented and tested, but real fixture inspection is TCC-blocked. |
| D — Ambiguous control | Automated pass only | Duplicate identifiers/labels return ambiguity and execute nothing. Real fixture ambiguity is TCC-blocked. |
| E — Moving element | Automated pass only | Identity ignores coordinates/layout and survives semantic reordering. Real fixture action is TCC-blocked. |
| F — TextEdit | Unsupported in this environment | TextEdit launch/running/focus are real NSWorkspace capabilities. AX document read/set remains experimental; no exact read-back was possible without TCC, so no document-success claim is made. |
| G — VS Code workspace | Partial pass | Real workspace association passed. Current VS Code foreground transition could not be verified while loginwindow was frontmost; an earlier unlocked focus restoration to Code passed. |
| H — Permission revocation | Simulated pass; real revocation not applicable | A granted→revoked typed probe and revocation immediately before mutation both fail before adapter mutation; deterministic persona wording passes. A real grant never existed to revoke. |

## Security and adversarial evidence

- AX labels and descriptions containing directives remain untrusted data and
  cannot create aliases, capabilities, targets, actions, focus policies, risk,
  approval, or authorization.
- Secure text, password-like fields, authentication/verification-code fields,
  and unsupported values are redacted before snapshot construction.
- Cross-app references, removed/replaced/stale elements, duplicate identifiers,
  hidden/disabled elements, oversized trees, and excessive fuzzy candidates
  fail closed or require semantic re-resolution/clarification.
- A focused modal hides background-window targets. The modal itself requires a
  separately profile-authorized selector.
- Coordinate and frame fields are absent and rejected as extra arguments.
- Permission revocation is probed again immediately before mutation; the test
  records zero adapter mutations.
- Cancellation during resolution produces no later mutation. Cancellation
  during independent verification remains observable and does not fabricate
  restoration or success.
- Application-profile copies cannot mutate registry authority. Forbidden
  capability, action, verifier, target, risk, and focus substitutions fail.
- Semantic waits stop at 30 seconds or 600 attempts. Traversal, strings,
  windows, nodes, actions, candidates, verifier count, retries, and tool
  execution are all separately bounded.
- Diagnostics retain one redacted in-memory semantic snapshot. Contracts and
  stores contain no screenshot, coordinate, raw-tree history, hidden reasoning,
  or secure value.
- Persona AX outcomes are deterministic and model-free. A `COMPLETED` state or
  AX API return cannot produce verified wording without independent per-step
  verification and required focus evidence.

## Retention inspection

No screenshot was taken or stored during these capstones. The foreground
broker has no screenshot/image field. Operation-local AX snapshots are not
persisted; the desktop diagnostic store replaces exactly one semantic summary
and omits labels, values, windows, elements, and raw trees. The repository
contains no capstone-generated screenshot or AX tree artifact.

## Remaining real gate

The unstable Python host described in the original run has now been replaced
by the background helper `me.adityalabs.omnimac.axhelper`. Its release build,
bundle identifier, ad-hoc development signature, mode-0600 Unix socket, peer
UID authentication, launch, and live `trusted=false` response were verified.
The daemon has no Python fallback. See `TCC_HOST_IDENTITY.md` and
`PHASE_5_4_TCC_CLOSURE.md`.

To close Phase 5.4, the user must first unlock the interactive desktop and
explicitly grant Accessibility trust to that exact packaged helper in System
Settings. Then rerun B–H against the packaged fixture,
TextEdit, and VS Code, record independent UI and final-focus evidence, and
promote only the exact capabilities that pass. Until then the honest claim
remains the Phase 5.3 claim; universal computer control and semantic real-AX
operation are not claimed.
