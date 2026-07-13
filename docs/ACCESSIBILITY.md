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

Each application profile binds that capability to the exact dotted tool,
semantic identifier and/or role allowlists, AX action allowlist, verifier
allowlist, risk floor, and focus policy. Authorization occurs once against the
query and again against the freshly resolved element. A matching label alone
cannot expand this trusted rule. Missing rules, target substitutions, action
substitutions, verifier substitutions, and tool/profile metadata conflicts fail
closed. Profiles returned through status APIs are copies, not live registry
authority.

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

The earlier underscore-named Phase 4 AX tools are not registered in the
production daemon because they predate bundle-bound application profiles. They
remain testable compatibility code only. Terminal continues to use restricted
subprocess execution, and Chromium continues to prefer browser DOM automation;
neither gains generic UI mutation through AX.

## Focus and cancellation ordering

Immediately before a semantic AX execution, the orchestrator snapshots the
frontmost application, refreshes profile authority and TCC trust, and only then
performs a temporary bundle-bound focus transition when the registered policy
is `RESTORE_PREVIOUS_FOCUS`. Failure to validate permission, capability, or
target focus runs no AX tool. Independent AX verification re-reads UI state
while the target remains frontmost; restoration and final-frontmost
verification occur afterward. Each stage has a separate audit event.

AX controller work runs outside the asyncio event loop. Mutation calls share a
cancellation flag checked before and after semantic resolution, after the
fresh permission probe, and immediately before the adapter mutation. This
prevents a cancelled inspection from later becoming a mutation. macOS AX
messages themselves are atomic synchronous calls and cannot be interrupted
mid-message; cancellation never fabricates rollback or verification evidence.

## Desktop status and diagnostics

`GET /api/accessibility` returns a fresh typed permission probe, copied
application profiles, and one bounded in-memory semantic diagnostic snapshot.
The snapshot may contain task/step/tool identifiers, bundle ID, semantic
identifier/role/alias, resolution method/confidence/candidate count, focus
policy, deterministic verification evidence, permission error, and ambiguity.
It has no labels, values, windows, elements, screenshots, raw AX tree, or hidden
reasoning and is never persisted.

The desktop Accessibility view displays permission and capability classes as
live daemon data. Resolver confidence and verifier evidence are hidden until
the user enables the developer-diagnostics switch. The only settings side
effect is a button that sends literal `user_requested: true`; malformed or
implicit requests cannot open System Settings, and the daemon still does not
click TCC controls or claim that opening the pane granted trust.

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

## Persona boundary

Terminal AX outcomes are mapped to a closed deterministic response enum after
execution and verification. Missing or revoked permission, missing, ambiguous,
disabled, stale, or unsupported elements, application closure, cancellation,
partial completion, failed focus restoration, and verified completion each
have fixed display and shorter spoken wording. Raw planner titles, element
labels, descriptions, values, and failure prose are not presentation facts.
Known bundle identifiers map to local display names; unknown identifiers use
the neutral phrase `the approved application`.

An AX API return is never sufficient for success language. A task in
`COMPLETED` receives verified AX wording only when every AX step has an
independent passing verification result and any required focus result passed.
All AX failure, refusal, clarification, cancellation, and routine response
paths remain model-free.
