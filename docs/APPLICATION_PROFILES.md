# Application capability profiles

THOTH uses immutable, versioned application profiles as the authority for app-specific capabilities. A model, window title, webpage, tool result, or application cannot add a capability or change its status. Unknown applications and undeclared capabilities fail closed.

Statuses:

- **Verified:** exercised against real OS state and paired with an independent verifier.
- **Experimental:** implemented or plausible, but unavailable unless an explicit trusted opt-in permits it.
- **Forbidden:** never routed for that application.

## Initial profiles

| Application | Bundle identifier | Verified | Experimental | Important forbidden operations |
|---|---|---|---|---|
| Finder | `com.apple.finder` | running/foreground detection, launch, focus | current folder, selected files | coordinate clicking, permission changes |
| TextEdit | `com.apple.TextEdit` | running/foreground detection, launch, focus | AX read/edit | unrestricted document access |
| Visual Studio Code | `com.microsoft.VSCode` | running/foreground detection, launch, focus | authoritative workspace match, editor read/edit | unrestricted editor control, extension install |
| Terminal | `com.apple.Terminal` | running/foreground detection, launch, focus | safe working-directory metadata | shell execution through UI, terminal-history reads |
| THOTH Accessibility Test App | `org.python.python` | none yet | AX inspect/read/edit/press | production use, launch by non-unique bundle id |
| Chromium | `org.chromium.Chromium` | background read-only operations | background interaction, foreground presentation, forms, submission | bypassing two-phase submission, profile/credential access |

The dev AX test app is currently a Tk process and does not have a unique packaged bundle identifier. Its profile therefore marks no capability verified and forbids bundle-based launch; `org.python.python` is recorded only to identify the current host process shape. It must be packaged with a unique bundle identifier before that profile can authorize launch/focus.

VS Code workspace matching remains experimental until the authoritative matcher is implemented and a real THOTH workspace match is recorded. Chromium form interaction and submission remain experimental despite unit/fixture coverage; they are not described as generally verified web control.

## Authority and verification

Every verified capability has a typed verifier mapping such as an NSWorkspace running/frontmost probe or browser URL probe. Experimental verifier mappings are optional because the capability is unavailable by default. A missing verifier for a verified capability, duplicate profile, missing bundle identifier, overlapping status, or invalid version makes the profile invalid at startup/test time.

Focus behaviour in a profile is a default for ambiguous app-level requests. The registered tool's `focus_policy` remains authoritative for a concrete invocation and cannot be weakened by a model proposal.
