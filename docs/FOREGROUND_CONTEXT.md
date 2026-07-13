# Seamless computer control — architecture specification

**Status:** Specification (implemented in slices 6–7, gated after 5.0/5.1). Builds on the Phase 4 app-control + AX adapters; adds no new risk downgrade path.

## ForegroundContextBroker

A read-mostly broker that snapshots the current foreground context on demand (never continuously, never screenshots). Fields: active application bundle id, active window title, focused Accessibility role, selected file URLs (only when safely obtainable via AX/Finder without extra permission), current browser domain (from the interactive session), associated workspace (resolved from path/app), current THOTH task, previous foreground application. All of it is UNTRUSTED, read-only context used to resolve references ("open it", "this project") — it can never approve actions or expand scope.

## Focus-change protocol (every focus-changing action)

1. Record current foreground context (broker snapshot).
2. Decide whether a focus change is actually necessary (skip if the target is already frontmost).
3. Perform the action (existing app_launch / app_focus / AX tools — same risk levels, same scope enforcement).
4. Restore focus to the previous application when appropriate (configurable; default restore for background operations).
5. Verify the final foreground state where required (ACCESSIBILITY_VALUE / APPLICATION_RUNNING verifiers — reuse Phase 4 framework).

Screenshots are never captured or retained. Selected-file URLs are read only when obtainable without new TCC prompts.

## Application capability profiles

Each supported app declares, as data (Pydantic model, versioned): verified capabilities, experimental capabilities, forbidden actions, preferred integration order (e.g. native AX → URL scheme → shell CLI), required permissions, and verification methods. The router/planner may only propose an app action that the profile marks verified (experimental behind an explicit opt-in). Forbidden actions are refused before policy review.

Initial profiles: Finder, TextEdit, Visual Studio Code, Terminal, THOTH Accessibility Test App, a supported Chromium browser. No universal-control claim — an app without a profile has no THOTH-driven capabilities beyond launch/focus.

## Boundary

The broker and profiles sit BEFORE the existing pipeline: they resolve references and constrain proposals. Every resulting action still passes registry validation, policy risk review, scope enforcement, approvals, execution-only-in-EXECUTING, and independent verification unchanged.
