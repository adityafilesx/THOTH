# Codex Phase 5.3 recovery audit

**Date:** 2026-07-13

**Audit point:** `phase-5/persona` at `9548de0`

**Purpose:** Preserve the interrupted Claude Code work and establish the exact continuation state before production edits.

## Repository state

- Current branch: `phase-5/persona`.
- HEAD: `9548de0 feat(phase-5.2): persona response composer, factual-consistency summary, runtime status`.
- Local `main`: `f39f151 feat(phase-5): hybrid intent routing + local constrained planner (slices 3-4)`.
- Staged changes: none.
- Stashes: none.
- Remote changes: not inspected or modified; no push will be performed.

### Dirty files at takeover

Tracked modifications:

- `apps/daemon/src/thoth_daemon/macos/app_control.py`
- `apps/daemon/src/thoth_daemon/tools/app_tools.py`
- `apps/daemon/src/thoth_daemon/tools/base.py`
- `apps/daemon/src/thoth_daemon/tools/shell_tool.py`

Untracked partial work/configuration:

- `.agents/`
- `.codex/`
- `AGENTS.md`
- `apps/daemon/src/thoth_daemon/core/focus.py`
- `apps/daemon/src/thoth_daemon/core/foreground.py`
- `apps/daemon/tests/core/test_focus.py`
- `apps/daemon/tests/core/test_foreground.py`
- `apps/daemon/tests/core/test_foreground_live.py`

`git diff --cached` and `git stash list` were empty. No dirty file was discarded, reset, regenerated, or overwritten during this audit.

## Committed Phase 5.2 state

Two commits belong to the interrupted session and are preserved:

1. `d6fd920 docs: Phase 5.2-5.3 gap report + test plan (pre-implementation)`
   - Added `docs/PHASE_5_2_5_3_GAP_REPORT.md`.
2. `9548de0 feat(phase-5.2): persona response composer, factual-consistency summary, runtime status`
   - Added `core/persona.py`, `core/persona_summary.py`, and `core/runtime_status.py`.
   - Added persona, live-summary, and runtime-status tests.

The committed Phase 5.2 implementation contains deterministic templates, immutable fact passthrough, policy checks, optional locally generated summaries behind a validator, deterministic fallback, and minimal runtime health. The interrupted wording is already correct: `Stopped. No external action was taken.` Mixed partial-completion wording is also already supported. These files will not be rewritten unless integration tests expose a concrete defect.

## Uncommitted Phase 5.3 state

### Foreground context

`core/foreground.py` and its tests are substantial, preservable work:

- snapshot-on-demand capture over `AppControl.frontmost()`;
- no screenshot/image field and no continuous capture loop;
- title and selected-path redaction at capture time;
- bounded in-memory retention;
- previous foreground tracking;
- injected browser, selection, title, and workspace providers;
- real NSWorkspace foreground detection test.

The broker is read-only context and does not alter policy, approval, scope, or execution.

### Focus management

`core/focus.py` and its tests are substantial, preservable work:

- `FocusPolicy`, `FocusSnapshot`, `FocusTransition`, and `FocusRestorationResult`;
- KEEP, RESTORE, DO_NOT_STEAL, and ASK behaviours;
- independent final-frontmost checks for restoration and focus preservation;
- cancellation and ambiguous-intent fail-safe paths.

The `MockAppControl.set_frontmost(...)` helper affects only the in-memory mock. The real `AppKitAppControl` is unchanged by that helper.

### Interrupted tool integration

The current `ToolDefinition` has exactly one declaration:

```python
focus_policy: FocusPolicy = FocusPolicy.DO_NOT_STEAL_FOCUS
```

There is no duplicate declaration, stale string forward reference, `type: ignore` residue related to focus policy, dataclass/Pydantic field misuse, or mutable shared default. `FocusPolicy` is an enum value stored as a class-level tool contract field.

`app_launch` and `app_focus` explicitly declare `KEEP_NEW_FOCUS`. `shell_run` explicitly declares `DO_NOT_STEAL_FOCUS`. The base default protects all other tools, but browser semantics have not yet been made explicit per tool.

## Defects and incomplete work discovered

1. Ruff import ordering fails in `tools/app_tools.py` and `tools/shell_tool.py` after the interrupted imports.
2. `test_focus.py` and `test_foreground.py` call `pytest.main` without importing `pytest`.
3. `test_focus.py` binds an unused `transition` local.
4. Three committed Phase 5.2 test files contain Ruff drift (unused `noqa` directives and one import-order issue).
5. `ruff format --check apps/daemon` reports the pre-existing `tests/api/test_voice_api.py` as needing formatting; it is unrelated to the Phase 5.3 diff and must be handled without masking other changes.
6. `KEEP_NEW_FOCUS` currently returns `verified=True` without verifying that the requested target became frontmost. This is weaker than the stated independent-verification contract.
7. RESTORE records `restored=True` when restoration was attempted even if verification failed. The field semantics must be clarified or tightened so the desktop cannot imply successful restoration.
8. Browser tool policies are not explicit per semantic operation. `browser_read`/`browser_find` should remain background/read-only, while `browser_open` is user-presenting and should keep new focus. Temporary inspection needs a separate validated policy at invocation/integration time rather than a blanket browser policy.
9. The focus policy exists on registered tool classes but is not yet serialized across an API/schema boundary, included in the authoritative tool catalog, or enforced against a model proposal.
10. There are no application capability profiles, authoritative workspace matcher, operational dialogue state, lifecycle persona integration, Phase 5.3 API/desktop surfaces, or Phase 5.3 capstone record yet.
11. `AGENTS.md` exists as untracked recovery/configuration work and already contains the original safety guide, but it does not yet state every new requested prohibition verbatim (focus/persona/screen-capture/local-cloud constraints).

## Baseline verification

Commands were run against the untouched production state after repository inspection.

- Targeted persona/foreground/focus tests: **63 passed**.
- Full daemon suite: **688 passed**, 7 warnings.
  - One Starlette/httpx deprecation warning.
  - Six aiosqlite worker-thread warnings caused by event-loop shutdown during an existing browser test; not introduced by the focus files, but retained as gate noise to investigate if it persists.
- Strict mypy: **clean, 94 source files**.
- Import-cycle smoke test: imports of `FocusPolicy`, `ToolDefinition`, and `AppLaunch` succeed; values resolve to `do_not_steal_focus` and `keep_new_focus`.
- Ruff check: **failed with 9 findings**, enumerated above.
- Ruff format check: **failed**, one unrelated voice API test file would be reformatted.

The initial sandbox could not access the existing uv cache; the exact commands were rerun with access to the repository's established uv environment. No dependency or source mutation was required.

## Work that can be preserved

- Preserve both Phase 5.2 commits without amendment.
- Preserve the foreground broker, foreground redaction/retention tests, and live NSWorkspace capture test.
- Preserve the focus models, manager structure, cancellation/ambiguity handling, and mock-only `set_frontmost` helper.
- Preserve the single enum-typed base default and explicit app/shell overrides, then extend and test them rather than reimplementing the contract.
- Preserve `.claude/`; the new `.agents/` and `.codex/` files are configuration mirrors and will be reviewed before any commit.

## Exact continuation plan

1. Repair only the interrupted focus integration: add failing policy/verification/serialization tests, fix independent target verification and result semantics, make app/shell/browser policies explicit, expose authoritative policy through the tool catalog/API boundary, and prove model proposals cannot override it.
2. Run targeted tests, Ruff, format check on touched files, and strict mypy; commit the recovered foreground/focus slice separately.
3. Add six immutable, versioned application capability profiles with fail-closed validation and real-evidence labels; document them and commit separately.
4. Add authoritative workspace profiles/matching with approved-path authority, title-as-hint semantics, normalization and symlink protections; test spoofing, ambiguity, disappearance, and redaction.
5. Add in-memory, expiring, task-isolated operational dialogue state. Resolve only recent authoritative artifacts/workspaces; make constraints non-bypassable; prohibit vague approval and scope/risk expansion.
6. Integrate deterministic persona composition into task lifecycle/API state, using the local model only for complex verified summaries and never for approval/refusal/failure wording.
7. Regenerate shared schemas if cross-boundary Pydantic contracts change, then wire the desktop to live daemon fields with explicit proposed/approved/executed/verified distinctions.
8. Add adversarial coverage for persona, focus, foreground, workspace, profile, and dialogue boundaries.
9. Exercise real macOS capstones where permissions/environment permit; record skipped cases with exact reasons and never mark unverified capabilities verified.
10. Update ADRs and project truth documents, then run every completion gate before making the bounded Phase 5.2/5.3 claim.

Production code remained untouched until this audit was completed.
