# Accessibility embodiment

## Permission boundary

Accessibility is an optional macOS capability. THOTH must distinguish these
states deterministically:

- `not_determined`: trust is absent and this service has not opened the
  Accessibility settings route at the user's request.
- `denied`: trust remains absent after that explicit settings request.
- `granted`: the current OS trust probe succeeds.
- `revoked`: a process observed as granted later fails the OS trust probe.
- `unavailable`: the trust framework or probe cannot provide a result.

Every AX operation forces a fresh trust probe immediately before touching an
AX element. A cached snapshot exists only for bounded status presentation and
is never execution authority. A stale snapshot must be refreshed.

The service may open the Accessibility pane in System Settings once after an
explicit user request. It does not click controls, alter TCC, repeatedly prompt,
or claim that opening Settings granted access. Permission absence blocks only
AX operations; NSWorkspace application inventory/focus, filesystem, Git,
restricted shell, browser, persona, and other non-AX capabilities continue
through their existing boundaries.

The first real host probe on 2026-07-14 returned `not_determined`: the
ApplicationServices framework was available, but this daemon process did not
have Accessibility trust. No Settings window was opened because the user had
not requested that side effect. This is expected fail-closed evidence, not an
AX capability failure or a permission grant.

## Snapshot contracts and privacy budget

AX observations cross daemon/API boundaries only through strict typed
application, window, element, query, reference, action, verification, and
permission contracts. Every snapshot is fixed as
`TOOL_RESULT_UNTRUSTED`; application text cannot become authorization,
capability, selector policy, or approval.

Collection has hard ceilings of 12 levels, 500 elements, 4,096 UTF-8 bytes per
string, 32 actions per element, and 20 windows per application snapshot.
Truncation is explicit. Cyclic nodes are visited once. The collector does not
perform a second unbounded scan after reaching a ceiling.

Secure text fields and fields semantically marked as password, passcode,
one-time code, verification code, OTP, or token expose only redacted value
metadata. Unsupported raw values are also omitted. Contracts contain no frame,
coordinate, screenshot, hidden-system-data, or reasoning fields. References
carry capture and expiry times and must be re-resolved after expiry; no full AX
tree retention store is introduced.
