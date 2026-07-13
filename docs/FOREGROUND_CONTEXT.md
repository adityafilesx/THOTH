# Seamless computer control — architecture specification

**Status:** Implemented in Phase 5.3. Builds on the Phase 4 app-control adapter and adds no authorization, approval, scope, or risk path.

## ForegroundContextBroker

`ForegroundContextBroker` snapshots current context only when an API/task response requests it. It has no timer, background loop, screenshot/image field, or full Accessibility-tree field. Optional title/selection/browser providers are redacted at capture time. History is process-local and purged after a bounded retention window (120 seconds by default).

All foreground data is untrusted, read-only context. Window titles and bundle ids are hints; they cannot grant workspace scope, approve an action, change an objective, or expand a capability profile.

## Focus-change protocol (every focus-changing action)

1. The registered tool supplies the authoritative `FocusPolicy`; model proposals are overwritten.
2. Immediately before execution, the orchestrator records the current frontmost app.
3. `ASK_IF_AMBIGUOUS` runs no tool and requires explicit direction.
4. The tool runs only through the existing `EXECUTING`-state path.
5. The manager independently checks `KEEP_NEW_FOCUS` or `DO_NOT_STEAL_FOCUS`, or restores and verifies `RESTORE_PREVIOUS_FOCUS`.
6. Every result emits immutable `focus.result` audit evidence and is exposed to presentation. An unverified focus result makes a completed task display as partial.

Shell and background-service tools remain `DO_NOT_STEAL_FOCUS`; they do not foreground Terminal. App launch/focus are `KEEP_NEW_FOCUS`. Browser policies are per operation rather than one blanket setting. Screenshots and full AX trees are never captured or retained by the broker.

## Application capability profiles

Each supported app declares, as data (Pydantic model, versioned): verified capabilities, experimental capabilities, forbidden actions, preferred integration order (e.g. native AX → URL scheme → shell CLI), required permissions, and verification methods. The router/planner may only propose an app action that the profile marks verified (experimental behind an explicit opt-in). Forbidden actions are refused before policy review.

Initial profiles: Finder, TextEdit, Visual Studio Code, Terminal, THOTH Accessibility Test App, a supported Chromium browser. No universal-control claim — an app without a profile has no THOTH-driven capabilities beyond launch/focus.

## Boundary

The broker and profiles sit BEFORE the existing pipeline: they resolve references and constrain proposals. Every resulting action still passes registry validation, policy risk review, scope enforcement, approvals, execution-only-in-EXECUTING, and independent verification unchanged.
