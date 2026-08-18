# Application capability profiles

OmniMac uses immutable, versioned application profiles as the authority for app-specific capabilities. A model, window title, webpage, tool result, or application cannot add a capability or change its status. Unknown applications and undeclared capabilities fail closed.

Statuses:

- **Verified:** exercised against real OS state and paired with an independent verifier.
- **Experimental:** implemented or plausible, but unavailable unless an explicit trusted opt-in permits it.
- **Forbidden:** never routed for that application.

## Initial profiles

| Application | Bundle identifier | Verified | Experimental | Important forbidden operations |
|---|---|---|---|---|
| Finder | `com.apple.finder` | running/foreground detection, launch, focus | bounded AX window snapshots, current folder, selected files | coordinate clicking, permission changes |
| TextEdit | `com.apple.TextEdit` | running/foreground detection, launch, focus | bounded window inspection and role-bound non-secure text read/set | unrestricted document access |
| Visual Studio Code | `com.microsoft.VSCode` | running/foreground detection, launch, focus, authoritative workspace match | bounded window inspection and role-bound text reads | unrestricted editor control, extension install |
| Terminal | `com.apple.Terminal` | running/foreground detection, launch, focus | safe working-directory metadata and bounded window-title inspection | shell execution through UI, terminal-history reads |
| OmniMac Accessibility Test App | `me.adityalabs.omnimac.axtest` | none yet | ten semantic AX capabilities against fixture identifiers | production use, coordinate control, credential dialogs |
| Chromium | `org.chromium.Chromium` | background read-only operations | browser interaction plus bounded AX window-title inspection | bypassing two-phase submission, profile/credential access |

The native SwiftUI AX fixture is packaged and ad-hoc signed with the unique bundle identifier `me.adityalabs.omnimac.axtest`. Its stable semantic identifiers are profile allowlisted. Its AX capabilities remain experimental because the daemon's real 2026-07-14 trust probe returned `not_determined`; unit evidence does not promote a capability to real-verified status.

Semantic AX execution is now hosted by the separate background bundle `me.adityalabs.omnimac.axhelper`, not uv Python. The helper cannot add or promote application profiles; it accepts only the already-authorized semantic operation over authenticated local IPC and returns untrusted bounded observations. Its current live trust probe is false, so this host change promotes no application capability.

VS Code workspace matching was exercised on 2026-07-13 against the real running `com.microsoft.VSCode` process and the approved OmniMac repository path. Authoritative sources were the approved path and active task workspace; the bundle id was a hint. Chromium form interaction and submission remain experimental despite unit/fixture coverage and are not described as generally verified web control.

The profile registry preserves private authoritative copies and returns deep copies at API/read boundaries. Model output and webpage/window content therefore cannot mutate the registry, self-add a capability, promote experimental status, or downgrade a forbidden operation.

## Semantic AX rules

Every declared `ax_*` capability must have an `AXCapabilityRule`. A rule binds one dotted tool name to explicit semantic action identifiers and/or roles, separate verifier-target allowlists, permitted AX actions, permitted independent verifier types, minimum risk, and focus policy. Separate targets allow a narrow Save-button action to be verified against a narrow status-label value without making either selector generic. Registration fails when a tool's risk or focus metadata conflicts with any profile rule. Execution authorizes the query before inspection and authorizes the resolved element again, including its actual role and identifier, before mutation.

The tool authority hook applies these rules during deterministic plan review, before policy or approval, and again during direct registry execution. This hook is shared by local and non-local planner paths; a model-proposed target cannot wait until the AX adapter to discover that it is unauthorized.

Finder, Terminal, and Chromium expose only bounded inspection rules while real AX permission/evidence is absent. TextEdit additionally has an experimental role-bound non-secure text read/set rule, and VS Code has experimental role-bound text reads; neither is verified. Terminal has no value-setting or action rule, so the restricted subprocess interface remains authoritative for shell execution. Chromium keeps `browser_dom` first and Accessibility second; AX does not duplicate DOM form automation. The fixture alone carries the broader narrow mutation rules needed for text, toggles, dropdown selection, Save/modal actions, delayed elements, and dynamic status verification.

The Phase 4 underscore-named generic AX tools remain as isolated compatibility code and unit fixtures, but are no longer registered by the production daemon. Production exposes only the ten profile-gated dotted semantic tools.

## Authority and verification

Every verified capability has a typed verifier mapping such as an NSWorkspace running/frontmost probe or browser URL probe. Experimental verifier mappings are optional because the capability is unavailable by default. A missing verifier for a verified capability, duplicate profile, missing bundle identifier, overlapping status, or invalid version makes the profile invalid at startup/test time.

Focus behaviour in a profile is a default for ambiguous app-level requests. The registered tool's `focus_policy` remains authoritative for a concrete invocation and cannot be weakened by a model proposal.
