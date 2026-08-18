# Accessibility TCC host identity

**Observed:** 2026-07-14

## Decision

Production semantic Accessibility calls now execute in a narrow background app:

| Property | Value |
|---|---|
| Process | `OmniMacAXHelper` |
| Bundle | `OmniMac Accessibility Helper.app` |
| Bundle identifier | `me.adityalabs.omnimac.axhelper` |
| Development signature | ad-hoc (`TeamIdentifier=not set`) |
| Production intent | stable helper host; Developer ID signing remains a packaging requirement |
| IPC | per-user Unix socket at `~/Library/Application Support/OmniMac/ax-helper.sock` |
| Socket permissions | observed `srw-------`, owned by the current user |
| Peer authentication | `getpeereid`; peer effective UID must equal helper effective UID |
| Network listener | none |

Before this change, `AXIsProcessTrusted()` ran in uv-managed CPython 3.12.13 at
`/Users/aditya1981/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/bin/python3.12`.
That binary had no bundle identifier or team identity and was not a stable
production TCC host. The daemon no longer falls back to that identity. If the
helper socket is absent, incorrectly owned, not mode-0600, malformed, or
untrusted, semantic AX is typed unavailable and no AX call executes.

## Helper authority ceiling

Protocol version 1 accepts only `health`, bounded application inspection,
semantic value setting, semantic action, and semantic option selection. Every
target is bundle/role/identifier-or-label/parent-path data. Extra fields and
unknown operations are rejected. Coordinates, frames, shell commands,
planning, approval, risk changes, profile changes, and instruction
interpretation do not exist in the protocol.

The daemon remains responsible for state-machine, profile, scope, policy,
approval, focus, and verifier gates. The helper re-resolves semantics, limits
inspection to 20 windows/500 elements/depth 12, isolates a focused modal,
redacts secure semantics, and probes `AXIsProcessTrusted()` immediately before
mutation. Helper results retain `TOOL_RESULT_UNTRUSTED` provenance.

## Packaging and manual trust

`apps/ax-helper/scripts/package.sh` builds and signs the background `.app`.
The observed development artifact passed `codesign --verify --deep --strict`
and reported the required bundle identifier. A release must set
`OmniMac_CODESIGN_IDENTITY` to a stable Developer ID identity; ad-hoc signing is
not release evidence.

The live helper launched successfully and reported `trusted=false`. No TCC
database was modified, no permission control was clicked, and no prompt was
automated. The user must manually add the exact packaged helper in System
Settings. Only a subsequent probe from that helper can establish trust.
