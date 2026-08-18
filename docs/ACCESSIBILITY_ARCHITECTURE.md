# Accessibility architecture

Phase 5.4 adds narrow semantic macOS Accessibility (AX) control without
changing OmniMac's execution state machine. The planner still produces data;
only the registered tool router may cross the AX boundary, and only while the
task is in `EXECUTING`.

## Authority flow

```text
typed plan step (untrusted proposal)
  -> dotted tool schema (no coordinates or extra arguments)
  -> immutable application profile (bundle + capability + target + action)
  -> policy, scope, and approval gates
  -> fresh TCC trust probe
  -> focus snapshot and bundle-bound transition when required
  -> bounded semantic snapshot and resolution
  -> repeated profile check against the freshly resolved element
  -> one AX action
  -> fresh independent AX verification
  -> focus restoration and final-frontmost verification
  -> deterministic persona result
```

The application profile, registered tool definition, approved application
scope, and current OS permission are authority. Model output, AX labels and
descriptions, window titles, application values, screenshots, and prior object
references are not authority.

## Components

- `AXPermissionService` observes `AXIsProcessTrusted`. Every real operation
  forces a fresh probe. Opening System Settings requires a literal explicit
  user request and never automates TCC controls.
- `RealSemanticAXAdapter` performs bounded PyObjC AX inspection and actions.
  `MockSemanticAXAdapter` is test-only and is named accordingly.
- Snapshot contracts remove coordinates, redact secure values, label all AX
  observations `TOOL_RESULT_UNTRUSTED`, and cap depth, nodes, strings, actions,
  parent paths, and windows.
- `AXResolver` uses stable identifier, exact or normalized role/label, trusted
  profile alias, parent path, then bounded fuzzy matching. Duplicate or close
  matches require clarification. A focused modal hides background-window
  targets so an old selector cannot reach through an unexpected dialog.
- Ten dotted semantic tools separate inspection, resolution, value reads,
  mutations, bounded waits, and supported-action listing. The old underscore
  tools are compatibility-test code and are absent from the production
  registry.
- `AXVerifierDispatcher` re-inspects and re-resolves current UI state. Tool
  return values cannot verify their own mutation.
- `AXDiagnosticsStore` replaces one in-memory redacted semantic summary; it
  never stores a raw tree, screenshot, label, value, or history.

## Resource ceilings

| Resource | Ceiling |
|---|---:|
| AX traversal depth / parent path | 12 |
| Elements per window/application resolution set | 500 |
| Windows per application | 20 |
| UTF-8 bytes per captured string | 4,096 |
| Actions per element | 32 |
| Fuzzy candidates | 50 |
| Semantic wait duration | 30 seconds |
| Resolution polls in one wait | 600 |
| Additional mutation verifiers | 8 |
| Registered tool timeout for mutation | 10 seconds |
| Recovery retries per step | 2 |
| Retained diagnostic snapshots | 1 |

Mutation tools do not retry internally. A synchronous macOS AX message is an
atomic call; cancellation is checked before resolution, after resolution,
after the fresh permission probe, and immediately before mutation. Any later
recovery is the existing bounded orchestrator recovery path and must repeat all
authority and verification gates.

## Application boundaries

Finder and Terminal expose snapshot-only AX rules. Terminal UI is never used
to execute shell commands; the restricted subprocess tool remains
authoritative. Chromium uses Playwright/DOM first for browser semantics,
two-phase form submission, and URL/domain verification; AX is limited to
bounded window inspection. TextEdit and VS Code AX operations remain
experimental until real TCC-backed evidence supports exact capabilities. The
packaged fixture alone has the broader test-only semantic mutation rules.

## Retention and presentation

There is no continuous AX capture and no screenshot capture. Operation-local
snapshots are discarded after the call. The desktop receives only live
permission/profile state plus the single bounded diagnostic summary. Terminal
AX outcomes enter a closed deterministic persona enum; verified wording
requires independent UI and required focus verification.
