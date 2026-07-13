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
