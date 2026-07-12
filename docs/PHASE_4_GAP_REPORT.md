# THOTH Phase 4 — Gap Report & Execution Plan

**Date:** 2026-07-12 · **Base:** `main` @ `dba63cb` (Phases 0–3 complete, 451 tests green)
**Author:** THOTH engineering (paired) · **Status:** pre-implementation audit (no code changed yet)

This document audits the Phase-3 implementation against the Phase-4 specification, records the gap per
slice with acceptance criteria and verifiability, and defines the execution plan. **Nothing is
implemented until this report and its plan are reviewed.**

---

## 0. The central risk — environment-gated live verification

Phase 4's **primary objective** is *five real end-to-end workflows, each starting from natural
language and finishing with independently-verified OS/browser state, using the **live** Claude
planner.* Several slices therefore depend on capabilities **this environment did not provide in
Phase 3**, and the objective cannot be *proven* without them:

| Dependency | Needed by | Status in this env (Phase 3) | If absent |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Slice 1 (live planner eval, ~100 real calls), Slice 10 (all 5 capstones use the live planner) | **Not present** | Planner logic stays fully unit-tested with an injected fake; *live* planning, eval percentages, and capstones **cannot run** |
| macOS **Accessibility TCC** grant | Slice 3 (`ax.set_value`/`perform_action`), Slice 10 capstone 4 | **Not granted** (launch/focus/list need no TCC and are verified) | AX adapter built + unit-tested vs a mock AX tree; live AX **unverifiable** |
| **Microphone** + local STT model (whisper.cpp / faster-whisper) | Slice 6 (voice) | mic **not granted**; STT model not installed (macOS `say` TTS is available) | Voice pipeline built behind adapters + unit-tested; live capture/transcription **unverifiable** |
| Approved **editor** running (VS Code) | Slice 10 capstone "Continue THOTH" | present (`app_launch` verified in Phase 3) | ok |
| **Cost / rate limits** on the live planner | Slices 1, 10 | n/a | ~100 planner calls + capstone re-plans have real token cost |

**This is the make-or-break decision for the phase.** Everything that is *code* (adapters, engines,
verifiers, hash chain, correlation IDs, telemetry, test apps, hardening) is fully buildable and
unit-testable here. The **live** planner eval and the **five live capstones** — the phase's headline
deliverable — require at least the API key (and TCC/mic for the AX and voice capstones).

**Recommended posture (matches the Phase-3 pattern you approved):** build + unit-test **every** slice
to completion; run each live verification the moment its environment is available; label anything not
live-verified as *"implemented, pending live verification"* in STATUS/CAPSTONE_REPORT; never overclaim.
The final claim ("THOTH can safely execute and verify selected multi-step workflows…") is only made
after the five live capstones actually pass.

---

## 1. Gap-by-slice audit

Legend — **Verifiability:** 🟢 fully here · 🟡 partial (unit-test now, live pending env) · 🔴 live-only (needs key/TCC/mic).

### Slice 1 — Live planner evaluation 🟡
- **Have:** `ClaudePlanner` behind `PlannerAdapter`; `AnthropicPlannerClient` (lazy, structured output, `claude-opus-4-8`); injected `PlannerClient` protocol; unit tests for mapping/validation/untrusted-rejection/raise-safety; `THOTH_PLANNER=claude` switch.
- **Gap:** no evaluation framework; no ≥100 categorized requests; no metrics (valid-plan %, unknown-tool %, invalid-arg %, correct-risk %, correct-scope %, unnecessary-step %, injection-failure %); no `docs/evaluations`; secret-in-prompt/log/audit assertions not codified.
- **Acceptance:** eval harness runs ≥100 requests across all 13 categories; emits redacted report to `docs/evaluations`; API key never in logs/SQLite/frontend/prompt/audit (asserted).
- **Deps:** 🔴 live key for real percentages. Harness + categorized corpus + a **fake-planner dry-run mode** (deterministic scoring against expected tool/risk) are 🟢 — build now, run live when keyed.

### Slice 2 — End-to-end correlation 🟢
- **Have:** `Task`, `PlanStep`, `ApprovalRequest`, `ToolInvocation`, `ToolResult`, `VerificationResult`, `AuditEvent`, WS envelope. **No `correlation_id` anywhere.**
- **Gap:** add `correlation_id` (minted at request) propagated through task→planner→plan→step→approval→invocation→result→verification→recovery→audit→WS→frontend timeline; frontend must show proposed/approved/executed/verified per step.
- **Acceptance:** one id threads the whole loop; a test asserts every audit/WS event for a task carries the same id; frontend renders the four per-step states.
- **Deps:** schema + orchestrator + WS + desktop. Additive; keep `extra="forbid"` + regen shared-schemas.

### Slice 3 — Accessibility control 🟡
- **Have:** `app_control.py` (launch/focus/list via NSWorkspace, no TCC). **No AX element interaction.**
- **Gap:** a **THOTH Accessibility Test App** (text input, buttons, checkbox, dropdown, table, modal, save, dynamic status, moving elements, disabled elements); typed tools `ax.inspect_application`/`find_element`/`read_value`/`set_value`/`perform_action`/`wait_for_element` using AX roles/labels/identifiers (**never coordinates**); a permission setup-state view; workflow "Enter Aditya … and save" verified by reading status **through AX**.
- **Acceptance:** AX tools drive the test app by role/label/AXIdentifier; verifier reads resulting status via AX; graceful setup-state when TCC absent.
- **Deps:** 🔴 TCC for live drive. The AX adapter behind a protocol + a **MockAXTree** for unit tests is 🟢. Test app is a small native/SwiftUI (or Tauri) app — buildable; running it under AX needs TCC. PyObjC `ApplicationServices`/`AXUIElement`.

### Slice 4 — Browser interaction 🟡
- **Have:** `browser_read` (read-only, headless Chromium, domain allowlist, `WEB_UNTRUSTED`+redacted).
- **Gap:** `browser.open/read/find/click/fill/select/download/screenshot/prepare_submission/submit`; **`submit` kept separate** from fill/click and is **R2**; a local browser test app (forms, file upload, dropdowns, validation errors, dynamic content, confirmation, **simulated prompt-injection panel**); proof that page content cannot authorize submission / expand domains / invoke shell / request secrets / change intent / downgrade risk.
- **Acceptance:** interaction tools work on the local test app; external submit + upload are R2 (approval); injection-containment tests pass (page content is `WEB_UNTRUSTED`, never reaches policy/scope/approval).
- **Deps:** 🟢 Playwright already installs headless Chromium here; local test app is a served static/localhost page (buildable + drivable offline). Persistent browser session (vs per-call) is a design change — see Plan §Notes.

### Slice 5 — Skill engine 🟡→🟢
- **Have:** `SkillDefinition` schema, `SkillRow` table, `SkillStore` (list/toggle), read-only Skills view, `GET/PATCH /api/skills`. **No execution engine.**
- **Gap:** versioned declarative skills with typed inputs + JSON-Schema validation, variables, step deps, conditions, verification, retry config, approval boundaries, dry-run, cancellation, versioning, execution preview, audit history; skills reference **only registered tools/verifiers**; a skill's risk is **never below** its constituent actions; initial skills `continue-project`, `project-health-check`, `research-and-save`, `prepare-git-commit`, `organize-workspace`; wire Skills view to install/inspect/configure/dry-run/execute.
- **Acceptance:** skill compiles to a plan the **existing** orchestrator runs (no bypass); risk floor enforced; dry-run has no side effects; unit-tested with mock tools; live via the real tools/planner where relevant.
- **Deps:** mostly 🟢 (compiles to `ExecutionPlan` over real tools; runs through the safety core). `research-and-save` live path needs browser (ok) + possibly planner.

### Slice 6 — Voice 🔴 (pipeline 🟡)
- **Have:** none. `TaskSource.VOICE` enum + Settings placeholder only.
- **Gap:** push-to-talk capture → VAD → local STT → editable transcript → task submission (**same endpoint as text**) → streamed execution → **interruptible** `say` TTS; visible recording state; mic disabled when not recording; audio discarded post-transcription; Escape cancels recording / interrupts TTS; global Stop cancels execution; transcript reviewed before submit; **voice cannot approve R2/R3**; no always-on mic; no wake word; STT/TTS behind replaceable adapters.
- **Acceptance:** adapters + task-engine integration unit-tested; TTS via `say` verifiable here; STT/mic live-verifiable only with mic + model.
- **Deps:** 🔴 mic + STT model for live capture. `say` TTS 🟢. Adapters + transcript UI + "voice can't approve" guard 🟢.

### Slice 7 — Independent verification 🟡→🟢
- **Have:** `VerificationEngine` with `OUTPUT_ASSERTION` (real), `NONE_READONLY` (real), **`STATE_PROBE` placeholder (returns True)**.
- **Gap:** real independent verifiers — `FileExists`, `FileContent`, `ProcessRunning`, `PortListening`, `HttpHealth`, `GitState`, `ApplicationRunning`, `AccessibilityValue`, `BrowserURL`, `BrowserElement`, `ExitCode`, `Composite`; **a successful tool return ≠ task success**; every plan step declares an expected result + compatible verifier; structured evidence surfaced in the frontend. This turns `STATE_PROBE` into a real independent post-execution probe (the Phase-3 noted follow-up).
- **Acceptance:** verifiers run real read-only probes producing structured evidence; the engine routes independent verification (not the tool's own claim); frontend shows evidence.
- **Deps:** 🟢 (file/proc/port/http/git/app/browser probes run locally). `AccessibilityValue` live needs TCC (🔴 live, 🟢 mock). Requires extending `VerificationEngine.verify` to run async probes with registry/adapter access — a real change to a Phase-2 module (careful, well-tested).

### Slice 8 — Bounded recovery 🟡
- **Have:** `RecoveryController` (retryable→retry within per-step(2)/per-task(5) budget; denials fail; typed decisions).
- **Gap:** richer recovery actions (refresh-observed-state retry, re-resolve AX element, retry browser locator, approved alternative tool, **replan through PlannerAdapter**, request user intervention, abort safely); limits — **≤25 steps/task, ≤2 retries/step, ≤2 replans, recovery depth ≤3, configurable max duration**; new terminal state **`FAILED_REQUIRES_USER`**; **no infinite planner-executor loops**.
- **Acceptance:** limits enforced with tests hitting each; replan bounded; loop guard proven; `FAILED_REQUIRES_USER` reached at limit.
- **Deps:** 🟢 (replan uses the injected planner — mock in tests). Adds `FAILED_REQUIRES_USER` to `TaskState` + transition table + terminal set.

### Slice 9 — Tamper-evident audit 🟢
- **Have:** append-only `AuditStore` (per-task monotonic seq, redaction, no update/delete surface). **No hash chain.**
- **Gap:** hash chain — each event hash covers prev-hash + canonical payload + task id + correlation id + seq + timestamp; chain-validation function; exportable **redacted execution manifest** (request/intent/plan/policy/approvals/tool calls/results/verification evidence/recovery/final result/hash-validation status).
- **Acceptance:** chain validates; a mutated event breaks validation (test); manifest export is redacted + complete.
- **Deps:** 🟢. Migration 0003 (add `prev_hash`/`hash` columns) + canonical serialization. Depends on slice 2 (correlation id in the hash).

### Slice 10 — Capstone workflows 🔴 (build 🟢)
- **Gap:** 5 live workflows (Continue THOTH; Research-and-save; Prepare-commit; AX operation; Browser form) — each **natural language → live planner → … → verified state**, with a recorded redacted manifest each.
- **Acceptance:** each begins in NL, uses the live planner, ends verified; manifests stored.
- **Deps:** 🔴 live key (all), TCC (AX one), browser (ok), editor (ok), git (ok). Harness + fixtures + manifest recorder 🟢; the *runs* need the key/TCC.

### Slice 11 — Hardening 🟢 (mostly)
- **Gap:** adversarial tests — injection (web/repo/terminal), symlink scope escape, path traversal, arg injection, browser redirects, approval replay/param-mutation/stale, session-token theft, audit-chain modification, voice cancellation, daemon crash mid-exec, browser crash mid-exec, malformed planner output, AX permission revocation, kill-switch in each state.
- **Acceptance:** each attack is refused/contained with a test; many already partially covered (scope escapes, approval single-use, unknown tool) — extend to the full matrix.
- **Deps:** 🟢 (deterministic). AX-revocation live 🔴, mockable 🟢.

### Slice 12 — Final gate 🟡
- **Gap:** run the full gate (pytest, ruff, mypy, vitest, eslint, tsc, vite build, cargo check, migrations-from-empty, audit-chain validation, planner eval suite, **5 live capstones**); update README, STATUS, MILESTONES, DECISIONS, THREAT_MODEL, TEST_PLAN, PRIVACY, and a new **CAPSTONE_REPORT** stating exactly what was exercised, env/permissions/models/commands, results, failures, recovery, evidence paths, residual risks, unsupported capabilities.
- **Deps:** the 5 live capstones + planner eval are 🔴 (key/TCC). Everything else 🟢.

---

## 2. Cross-cutting foundations (build first — many slices depend on them)

1. **Correlation ID (slice 2)** — threads everything; slice 9's hash covers it; slice 10's manifest keys on it. **Do first.**
2. **Real verification framework (slice 7)** — turns the `STATE_PROBE` placeholder into real independent probes; every capstone's "verified state" depends on it. **Do early.**
3. **Bounded recovery + `FAILED_REQUIRES_USER` (slice 8)** — the loop/limit guards the capstones rely on.
4. **Hash chain + manifest (slice 9)** — evidence artifacts for slice 10.

## 3. Recommended sequence (each: isolated worktree → TDD → security + integration review → merge)

```
Foundations:   2 correlation → 7 verification framework → 8 recovery+limits → 9 hash-chain+manifest
Capabilities:  3 AX (app + adapter + tools) → 4 browser interaction → 5 skill engine → 6 voice
Live/verify:   1 planner eval (needs key) → 10 capstones (need key/TCC) 
Close:         11 hardening → 12 final gate
```
Rationale: correlation + verification + recovery + audit are prerequisites for *meaningful* capstones
and manifests. Capability adapters (AX, browser, skills, voice) are independent and parallelizable in
worktrees. The two 🔴 live slices (1, 10) come after the code they exercise exists, and run the moment
a key/TCC is available. Hardening + final gate close.

## 4. Acceptance-gate policy (unchanged from Phase 3)

Per slice: failing-test-first TDD; both allowed **and** rejected paths for safety changes; full suite +
ruff + mypy + desktop gate green; **security-reviewer** and **integration-reviewer** pass; STATUS/docs
updated truthfully; **no test weakening, no bypassPermissions, no push**; live-only steps labeled
*pending live verification* until actually run.

## 5. Invariant guardrails re-affirmed for every slice

Planner stays planning-only (no tool invoke / approve / risk-lower / scope-expand / new-tool /
verification-disable / policy-modify). All execution through the existing orchestrator + state machine
+ policy + approvals + scope enforcer + registry. No execution outside EXECUTING. R3 blocked. R2 needs
fresh single-use approval. Voice cannot approve R2/R3. External content is `WEB_UNTRUSTED`/`FILE_UNTRUSTED`
and cannot change objectives, approve, expand scope, or request secrets.

## 6. Decision required before coding

The four foundation slices (2,7,8,9) and the capability adapters (3,4,5,6) are fully buildable and
unit-testable **now**. The phase's headline — **live planner eval (slice 1) and the five live
capstones (slice 10)** — needs at minimum an `ANTHROPIC_API_KEY`, plus **Accessibility TCC** for the AX
capstone and **mic + STT model** for voice. **How should live verification be handled?** (See the
question posed alongside this report.)
