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

## Semantic resolution

The resolver accepts only a capability-authorized query and a bounded current
snapshot. Priority is stable identifier, exact role/label, normalized
role/label, trusted application-profile alias, exact parent path, then a fuzzy
comparison limited to 50 same-role candidates. Fuzzy matches require a score
of at least 0.88 and a clear separation from the runner-up.

Duplicate or near-tied candidates return ambiguity and require clarification.
Hidden observations are re-resolved, observations older than two seconds are
stale, and disabled controls cannot be selected for activation. A missing or
expired object reference may only recover through the original semantic query;
it never becomes a live authority. Cross-application references, undeclared
aliases, denied capabilities, and snapshots above 500 elements fail closed.
Labels remain inert untrusted strings and cannot define aliases or selector
rules. No visual coordinate or window size participates in identity.

## Tool boundary

The daemon registers ten narrow semantic tools:

```text
ax.inspect_application   ax.inspect_window
ax.find_element          ax.read_value
ax.set_value             ax.perform_action
ax.select_option         ax.wait_for_element
ax.wait_for_value        ax.list_supported_actions
```

Every input binds an exact bundle identifier and a literal tool-specific
capability. A mutation tool therefore cannot claim a read capability or a
model-chosen substitute. Registry scope is the same bundle identifier, while
the immutable application profile must independently authorize the capability.

Reads are R0 and preserve current focus. The three reversible local mutation
tools are R1, support inert dry runs, and restore prior focus. External side
effects are not authorized through these generic R1 capabilities; submission,
credential-dialog, and system-security operations remain unavailable or
forbidden by profile. Mutation results deliberately say independent
verification is pending and contain no `verified` success flag.

The real adapter probes current TCC trust both in the controller and again at
the OS operation boundary. It enumerates at most 20 windows and 500 elements,
uses bounded attribute-value APIs for child lists, suppresses sensitive values
before constructing raw nodes, and re-finds action targets by identifier or a
unique role/label match. The deterministic mock is explicitly named and used
only by tests.

## Independent verification

Semantic mutations register an independent tool verifier with the
orchestrator. After the action returns, the verifier performs a new permission
check, re-inspects current AX state, re-resolves the semantic target, and only
then evaluates the declared postcondition. The action result is never used as
the observed state. A successful AX API return with a mismatched fresh value
therefore enters bounded recovery instead of completion.

The verifier set covers element existence, value, enabled, focused, selected,
window existence, and application-frontmost state. Composite verification
requires every child. `ax.set_value` and `ax.select_option` require a primary
`value_equals` verifier bound to the same target and exact requested value.
Other mutations may not use existence alone as proof. Up to eight additional
postconditions may make verification stricter. Verification exceptions,
permission revocation, unavailable probes, redacted values, and target
ambiguity all fail closed without logging raw expected or observed values.
