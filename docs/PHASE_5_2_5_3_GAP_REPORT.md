# Phase 5.2–5.3 gap report and test plan

**Date:** 2026-07-13 · Audit of main @ `f39f151` (680 tests) against the Phase 5.2 (persona) + 5.3 (seamless foreground control) spec.

## Environment (measured)

| Item | State |
|---|---|
| Local model | Ollama 0.31.1 up; qwen3:4b + qwen3:8b pulled → persona local-summary path verifiable live |
| App control | `macos/app_control.py` NSWorkspace: `frontmost()` returns `AppInfo(name, bundle_id, active)`, `list_running`, `launch`, `activate` — real, no TCC. Real frontmost + bundle id confirmed |
| AX adapter | `macos/ax.py` (Phase 4 slice 3) present; element interaction pending TCC |
| Persona / foreground / dialogue / focus | **none exist** — full build |

## Gap audit

| Requirement | State | Gap |
|---|---|---|
| PersonaResponseComposer, ResponsePolicyEngine, response modes/intents, facts, spoken/display split | none | **Build** (5.2). Deterministic templates first; optional local-model summary behind a factual-consistency validator that falls back to templates. Composer takes frozen facts and cannot mutate them. |
| Foreground context broker + typed ForegroundContext | none; NSWorkspace primitives exist | **Build** (5.3) over `frontmost()`/`list_running()`; snapshot-on-demand only, no screenshots, window-title/filename redaction + retention. |
| Focus policy (KEEP/RESTORE/DO_NOT_STEAL/ASK) + snapshot/transition/restoration + per-tool policy | none | **Build** (5.3). Focus-changing tools declare a `focus_policy`; restoration independently verified via `frontmost()`. |
| Application capability profiles (versioned) for 6 apps | none | **Build** (5.3). Data models; capabilities marked `verified` only when exercised on the real OS (launch/focus already are; AX element = experimental until TCC). |
| Operational dialogue state (short-lived, expiring) | none | **Build** (5.3). In-memory, TTL, reference resolution ("open it"), ambiguity → clarify, expiry rejects stale. Not long-term memory. |
| Local runtime status (UNAVAILABLE/STARTING/READY/GENERATING/DEGRADED/FAILED) | none | **Build** minimal status/health boundary only (no full LocalAIRuntimeManager). Persona reports degraded honestly. |
| Desktop: spoken+detailed response, foreground app, matched workspace, focus policy/result, model state, dialogue expiry, proposed/executed/verified labels | partial (labels exist) | Add persona + foreground surfaces (read-only). |
| Safety engine, PlannerAdapter, validator, policy, approvals, verifiers, scope, audit | complete | **Untouched.** Persona is composition-only; foreground is read-only context; focus goes through existing app/AX tools + scope + approvals. |

## Slice plan (TDD, isolated commits)

1. **Persona core** — schemas (ResponseMode/Intent, ResponseFact, PersonaResponse, SpokenResponse, DisplayResponse), `PersonaResponseComposer` deterministic templates for all 12 intents + the 11 named template categories, `ResponsePolicyEngine` (banned filler, no-success-without-verification, no-completion-for-proposed, no-approval-pressure, spoken length cap, display/spoken separation). Immutability test (composer cannot mutate facts).
2. **Persona local summary** — optional local-model phrasing of complex verified facts through the InferenceProvider, gated by a `FactualConsistencyValidator` (no claim absent from the facts; no banned filler; length); failure → deterministic fallback. Live qwen3:4b test.
3. **Local runtime status** — `LocalRuntimeStatus` enum + `LocalRuntimeMonitor.status()` from provider health; persona `DEGRADED_MODE`/`local-model unavailable` templates.
4. **Foreground context broker** — `ForegroundContext` model + `ForegroundContextBroker.capture()` over app control; window-title/filename redaction + retention; workspace match; snapshot-only. Real-OS test (detect Finder/frontmost).
5. **Focus policy + restoration** — `FocusPolicy` enum, `FocusSnapshot`, `FocusTransition`, `FocusRestorationResult`, `FocusManager` (record → act → restore-if-policy → verify via frontmost). Real-OS restore test.
6. **Application capability profiles** — versioned `ApplicationProfile` models for the 6 apps; capability `verified|experimental|forbidden`; no self-expansion / no forbidden→allowed downgrade (tested). `docs/APPLICATION_PROFILES.md`.
7. **Operational dialogue state** — `DialogueState` (TTL, artifacts, pending clarification/approval, previous result); reference resolver ("open it" → last artifact), ambiguity → clarify, expiry rejects stale.
8. **API + desktop** — `/api/persona/compose` (compose from posted facts), `/api/foreground` (capture), `/api/dialogue` state; desktop read-only surfaces + tests.
9. **Capstone + docs** — real-OS evidence (`PHASE_5_2_5_3_CAPSTONE.md`), `PERSONA_EVALUATION.md`, ADRs, STATUS/MILESTONES/THREAT_MODEL/PRIVACY/README, full gate.

## Test plan (maps to spec's required tests)

**Persona:** no success language when verification failed · no completion language for proposed · no approval pressure · no hidden partial failure · no unsupported emotional claim · no "Certainly"/"As an AI" · R2 approval wording · R3 refusal wording · cancellation wording · consistent concise style · deterministic fallback after local-model failure · local-summary factual consistency (live) · max spoken length · display/spoken separation.

**Foreground/focus/dialogue:** capture detects real frontmost app + bundle id · window-title redaction · sensitive-filename redaction · no persisted screenshots (no such field/store) · retention trims titles · focus KEEP keeps · DO_NOT_STEAL never activates · RESTORE returns to previous (real OS) · restoration verified via frontmost · cancellation during focus transition · AX permission revocation → clean failure · profile no self-expansion · no forbidden→allowed downgrade · no focus action outside app permissions · dialogue resolve "open it" · ambiguous short ref → clarify · expired state rejects stale ref.

**Safety invariants (persona/foreground cannot cross):** persona cannot alter policy/risk/approval/verification/audit facts (immutability + policy-fact passthrough tests) · no model-generated false completion · no local-model content authorizes a tool (persona output is display-only, never fed to the tool router).

## Claim ceiling

After the gate: "OmniMac provides a consistent local persona, understands short-lived operational context, detects the active macOS workspace, and manages supported application focus without unnecessary disruption." No voice, no proactivity claims.
