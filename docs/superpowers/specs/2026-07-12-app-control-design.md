# Slice 6 — macOS app control (PyObjC/NSWorkspace) design/spec

**Date:** 2026-07-12 · **Phase:** 3 · **Status:** building (Stop-hook-driven; goal requires it)
**Depends on:** slices 1–2 (scope, auth), merged.
**Verifiable here:** YES for launch/focus/list (NSWorkspace needs **no** TCC). AX *element* interaction
(reading/clicking UI) DOES need Accessibility TCC → **out of this slice**, noted for later.

## 1. Scope

Typed adapters for **app launch, focus, and listing** via PyObjC `NSWorkspace`. Gated by the slice-1
scope enforcer through `requested_scope(apps=[name])` → an app must be in the workspace's
`approved_apps` (empty by default → all launches denied until granted). No AX element interaction
(needs TCC), no window manipulation.

## 2. Components

| File | New? | Responsibility |
|---|---|---|
| `apps/daemon/pyproject.toml` | edit | add `pyobjc-framework-Cocoa; sys_platform=='darwin'` (macOS-only, lazy import). |
| `src/thoth_daemon/macos/__init__.py` | new | package marker. |
| `src/thoth_daemon/macos/app_control.py` | new | `AppInfo`, `AppControl` protocol, `AppKitAppControl` (real, lazy AppKit import), `MockAppControl`, `default_app_control()`. |
| `src/thoth_daemon/tools/app_tools.py` | new | `AppList` (R0), `AppLaunch` (R1), `AppFocus` (R1) + `register_app_tools(registry, adapter=None)`. |
| `app.py` | edit | `register_app_tools(registry)`. |
| docs | edit | ADR-017, STATUS, MILESTONES, THREAT_MODEL. |

## 3. Adapter

`AppControl` protocol: `list_running() -> list[AppInfo]`, `frontmost() -> AppInfo | None`,
`launch(name: str) -> bool`, `activate(name: str) -> bool`. `AppInfo(name, bundle_id, active)`.

`AppKitAppControl` imports `AppKit` **inside** each method (so `import app_control` never fails on
non-darwin / no-pyobjc): `NSWorkspace.sharedWorkspace()` → `runningApplications()` (filter to those
with a `localizedName`), `frontmostApplication()`, `launchApplication_(name)`,
`activate` finds the running app by name and calls
`activateWithOptions_(NSApplicationActivateIgnoringOtherApps)`.

`MockAppControl(running=[...])` drives unit tests with no OS calls.

## 4. Tools

| Tool | Risk | Verify | I/O |
|---|---|---|---|
| `app_list` | R0 | NONE_READONLY | `{}` → `{running:[{name,bundle_id,active}]}` |
| `app_launch` | R1 | STATE_PROBE | `{app}` → `{app, launched}` · `requested_scope(apps=[app])` |
| `app_focus` | R1 | STATE_PROBE | `{app}` → `{app, focused}` · `requested_scope(apps=[app])` |

- `app_launch.run`: `dry_run` → `launched=False`, no OS call. Else `adapter.launch(app)`; **self-verify
  state probe**: the app now appears in `list_running()` names, else raise.
- `app_focus.run`: `adapter.activate(app)`; self-verify `frontmost().name == app`, else raise.
- Tools take an `AppControl` in `__init__` (default `default_app_control()`); tests inject `MockAppControl`.

Scope: `app_launch`/`app_focus` request `apps=[name]` → the slice-1 enforcer refuses any app not in
`approved_apps` (+ grants). `app_list` is R0 and unscoped (reads the process list only).

## 5. Testing / verification

- **Unit (MockAppControl, no OS):** list maps AppInfo→output; launch success + state-probe pass;
  launch that doesn't appear running → failed; focus sets frontmost → pass; wrong frontmost → fail;
  dry-run no-op; `requested_scope(apps=[name])`.
- **Scope (backstop):** `app_launch` for an app not in `allowed.apps` → `scope violation`; in-scope ok.
- **Real-OS (guarded `@pytest.mark.skipif` when AppKit/darwin absent):** `AppKitAppControl.list_running()`
  returns a non-empty list incl. a `frontmost`; **non-intrusive** — no launching new apps in the test.
- **Live-OS smoke (manual script):** real `app_list`; `app_focus` on an already-running system app
  (e.g. Finder) → frontmost changes and back; confirm an un-granted app is refused by scope.

## 6. Honesty

Launch/focus/list are **verified against the real OS** (NSWorkspace, no TCC). This is NOT autonomous
control — still no planner wiring goals→apps. AX element reading/clicking (needs Accessibility TCC)
is explicitly deferred; STATUS says so.

## 7. ADR-017

PyObjC `NSWorkspace` for app launch/focus/list (no TCC); AX element interaction deferred to a
TCC-gated follow-up. macOS-only dep, lazy import (non-darwin safe). Scope via `requested_scope(apps=)`.
Rejected: driving `open(1)` through the restricted shell (loses structured focus/verify + would be R2).
