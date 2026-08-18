# Phase 5.4 handoff audit

**Date:** 2026-07-14

**Branch:** `phase-5/persona`

**Starting HEAD:** `19933f8 docs: record phase 5.2 and 5.3 capstones`

## Repository state at takeover

The tracked working tree was clean. Two pre-existing untracked development
directories were present and are not part of this phase:

- `.agents/`
- `.codex/`

There was no staged diff and no tracked unstaged diff. No stash was applied or
modified. Phase 5.2 and Phase 5.3 are represented by local commits through
`19933f8`; nothing has been pushed by this continuation.

## Preserved Phase 5.3 state

The existing foreground broker, focus manager, application profiles, workspace
matcher, operational dialogue state, persona integration, and desktop status
surface are committed and remain the baseline. The Phase 5.3 close recorded
782 passing daemon tests, one locked-desktop live skip, 65 passing desktop
tests, and clean static-analysis/build/migration gates.

No malformed or duplicate focus-policy declaration remains in
`tools/base.py`. Every registered tool has an enum-typed authoritative focus
policy, and focus handling remains bound to the orchestrator execution path.

## Unlocked focus rerun

The previously blocked focus evidence was rerun on an unlocked desktop:

- NSWorkspace reported ChatGPT (`com.openai.codex`) as the actual foreground
  application at the initial probe.
- Both tests in `apps/daemon/tests/core/test_focus_live.py` passed.
- A stricter explicit sequence activated Code, captured
  `com.microsoft.VSCode`, temporarily focused TextEdit under
  `RESTORE_PREVIOUS_FOCUS`, and independently observed Code as the final
  frontmost application.
- The restoration result reported `restored=True`, `verified=True`, and final
  bundle id `com.microsoft.VSCode`.
- The real background-service test passed without stealing focus.

This closes the Phase 5.3 locked-desktop restoration gap. Finder-specific and
TextEdit leave-focused evidence should still be recorded independently rather
than inferred from the restoration sequence.

## Existing Accessibility work that can be preserved

Phase 4 already supplies a useful, tested foundation:

- `macos/ax.py` has an injected adapter boundary, a real PyObjC adapter, a
  deterministic mock, bounded depth, and a fail-closed TCC check.
- `tools/ax_tools.py` has six typed tools with R0/R1 floors, app scope,
  dry-run behavior for mutations, and state-probe verification declarations.
- Existing AX tests cover role/label reads, mutation, wait, permission failure,
  registration, dry-run inertness, and registry scope enforcement.
- Application profiles already forbid Terminal UI shell execution and prefer
  browser DOM automation for Chromium.

These files will be extended in isolated TDD slices; they will not be blindly
regenerated.

## Accessibility gaps and defects found

- The development test app is Tkinter and appears as the non-unique
  `org.python.python` process. It cannot be an authoritative application
  target and is correctly not marked verified.
- Permission handling is binary (`trusted` or exception). It does not expose
  `NOT_DETERMINED`, `DENIED`, `GRANTED`, `REVOKED`, or `UNAVAILABLE`, and it has
  no separately authorized System Settings route.
- AX snapshots contain only role, label, value, and enabled. They lack stable
  identifiers, element references, window/application snapshots, action/value
  metadata, truncation markers, and explicit secure-value suppression.
- Real traversal has a depth limit but no element-count or per-string byte
  budget and can materialize more UI state than necessary.
- Resolution is exact role plus label only. It has no ambiguity result,
  profile aliases, parent path, bounded fuzzy matching, stale-reference guard,
  or bundle-id binding.
- The six legacy underscore-named tools do not cover the full Phase 5.4 typed
  surface. Mutation tools partly self-check, but the required independent AX
  verifier set is not yet implemented.
- Application profiles do not yet authorize the uniquely packaged test app or
  describe narrow per-application AX operations.
- The desktop has no Accessibility permission/capability/focus diagnostic
  section.

No defect justifies weakening the state machine, approval, risk, scope,
verification, audit, redaction, foreground-retention, or focus-policy
invariants.

## Exact continuation plan

1. Package a minimal native macOS Accessibility test application with bundle
   id `me.adityalabs.omnimac.axtest`, deterministic reset, and stable identifiers.
2. Add a typed permission boundary and fail-closed revocation handling.
3. Introduce bounded, redacted AX contracts and deterministic semantic
   resolution while retaining compatibility only where it is safe.
4. Add the required read/mutation tools and independent verifiers through the
   existing registry/orchestrator path.
5. Extend immutable application profiles and bind AX authorization to bundle
   id plus declared capability.
6. Integrate focus policy, cancellation, persona, API, and desktop diagnostics.
7. Add adversarial coverage, run real macOS capstones where permission allows,
   record exact evidence, and run every repository gate.

Each slice will start with a written contract and failing tests, implement the
minimum correct behavior, run targeted/adversarial tests, inspect the diff, and
be committed locally. No push, `sudo`, continuous screenshots, retained full
AX trees, coordinate clicks, voice, proactivity, or long-term memory are in
scope.
