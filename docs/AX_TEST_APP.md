# THOTH Accessibility Test App

## Slice 1 contract

The test fixture is a local, native macOS application used only to collect
repeatable Accessibility evidence. Its authoritative bundle identifier is
`me.adityalabs.thoth.axtest`; the older Tkinter fixture is not an authoritative
target because it shares `org.python.python` with unrelated Python processes.

The native fixture must package as `THOTH AX Test App.app`, expose stable
Accessibility identifiers for every relevant control, and reset to the same
state through both a visible Reset control and the `--reset` launch argument.
Tests and capstones must still inspect and operate the UI through AX. Reset is
setup, not an alternate action or verification channel.

Required semantic controls are a single-line input, multiline editor,
checkbox, toggle, picker, stepper, list, search field, disabled button, Save
button, modal sheet, confirmation alert, status label, progress indicator,
segmented control, layout-moving control, delayed element, disappearing
element, and validation error. Identifiers are lowercase `ax-*` strings and
must be unique within the application.

Packaging must be reproducible from source with the repository script, use no
network service, request no entitlement, and use no privileged operation. The
output bundle is a build artifact and is not committed.

## Control inventory

| Control | Accessibility identifier | Initial state |
|---|---|---|
| Single-line input | `ax-single-line-input` | empty |
| Multiline editor | `ax-multiline-input` | empty |
| Checkbox | `ax-checkbox` | off |
| Toggle | `ax-toggle` | off |
| Category picker | `ax-picker` | Alpha |
| Stepper | `ax-stepper` | 0 |
| Item list | `ax-item-list` | Mercury, Venus, Earth |
| Search | `ax-search-field` | empty |
| Disabled button | `ax-disabled-button` | disabled |
| Save | `ax-save-button` | enabled |
| Modal trigger | `ax-modal-button` | enabled |
| Confirmation trigger | `ax-confirm-alert-button` | enabled |
| Status | `ax-status-label` | idle |
| Progress | `ax-progress` | 25 percent |
| Segmented control | `ax-segmented-control` | Overview |
| Moving control | `ax-moving-control` | left aligned |
| Delayed element | `ax-delayed-control` | appears after 750 ms |
| Disappearing control | `ax-disappearing-control` | visible until pressed |
| Validation error | `ax-validation-error` | hidden until invalid save |
| Reset | `ax-reset-button` | enabled |

Modal content and its close action use `ax-modal-content` and
`ax-modal-close-button`. The native alert's semantic action labels are
`Cancel` and `Confirm`; the stable identifier is on its trigger because SwiftUI
does not expose modifiers for alert action buttons.

## Build and run

Build and ad-hoc sign the local bundle without privileges:

```bash
apps/ax-test-app/scripts/package_app.sh
```

The ignored output is:

```text
apps/ax-test-app/dist/THOTH AX Test App.app
```

Launch in deterministic initial state:

```bash
open -na "$PWD/apps/ax-test-app/dist/THOTH AX Test App.app" --args --reset
```

The visible Reset button reaches the same state. A 2026-07-14 packaging probe
verified the plist, ad-hoc signature, Launch Services name, and real running
bundle identifier `me.adityalabs.thoth.axtest`. That proves package identity;
it does not by itself mark any AX capability verified.
