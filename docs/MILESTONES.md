# THOTH Milestones

## Phase 0 — Foundations (docs, repo, Claude Code config)

- [x] Implementation plan (`docs/superpowers/plans/2026-07-11-thoth-phase-0-2.md`)
- [x] Repo root: README, CLAUDE.md, CONTRIBUTING, SECURITY, .env.example, Makefile, pnpm-workspace, pyproject, CI
- [x] Engineering docs: PRD, ARCHITECTURE, THREAT_MODEL, TOOL_CONTRACTS, PRIVACY, TEST_PLAN, MILESTONES, DECISIONS, STATUS
- [x] `.claude/agents` — architect, backend-engineer, desktop-engineer, macos-automation-engineer, security-reviewer, qa-engineer, integration-reviewer (all `model: fable`; architect + security-reviewer read-only)
- [x] `.claude/hooks` — credential/`sudo`/`rm -rf`/`git push`/publish/deploy blocking; command logging; post-edit formatting; pre-completion test reminder
- [x] `.claude/rules` + `.claude/skills`

## Phase 1 — Shells and plumbing

- [x] FastAPI daemon skeleton (`apps/daemon`): app factory, config, lifespan
- [x] `GET /api/health` (+ db check)
- [x] WebSocket event stream (`/ws`) + in-process EventBus
- [x] SQLite via SQLAlchemy 2 async + Alembic migration 0001
- [x] JSONL structured logging with redaction
- [x] Tauri 2 + React + Vite + Tailwind desktop shell
- [x] Desktop↔daemon connectivity (typed API client + reconnecting WS)
- [x] Command-center UI (input, state chips, Stop)
- [x] Plan + activity timeline UI on clearly-marked mock data
- [x] Daemon tests: health, WS, logging/redaction
- [x] Desktop tests: view rendering, badges

## Phase 2 — Safety core (mock tools only)

- [x] Pydantic contracts (14 models + enums + provenance) + shared-schemas export
- [x] Deterministic task state machine + audit-emitting transitions
- [x] Risk & policy engine (R0–R3, no downgrade, unknown-tool denial)
- [x] Prompt-injection guard (provenance firewall, directive flagging)
- [x] Approval engine (single-use, invocation-bound, TTL)
- [x] Tool registry + typed contracts + 9 mock tools
- [x] Verification engine + VerificationResult routing
- [x] Recovery controller (bounded retries; denials never retried)
- [x] Append-only audit store + redaction at all boundaries
- [x] Orchestrator + task API endpoints + WS task events
- [x] Frontend wired to real task flow (create, approve, deny, cancel, timeline)
- [x] Full test matrix green (see TEST_PLAN.md)

## Phase 3 — Real capability (IN PROGRESS)

- [x] **Slice 1 — Scope enforcement + permission store:** path-safety primitives (symlink-safe resolution + credential/system denylist), central `ScopeEnforcer` (orchestrator pre-EXECUTING gate + registry backstop), persistent `WorkspaceProfile`/`PermissionGrant` store, `/api/permissions` API. No real I/O yet.
- [x] **Slice 2 — Session auth token:** per-session bearer token, pure-ASGI HTTP middleware + WebSocket handshake (health exempt, constant-time compare), desktop attaches it via a Tauri command / dev env. Always-on. Closes threat T6.
- [x] **Slice 3 — Filesystem adapter (first real capability):** real scoped `fs_read_file`/`fs_list_dir`/`fs_write_file`/`fs_stat` — atomic self-verified writes, content redacted, gated by the slice-1 scope enforcer; verified against the real filesystem. Deletion/move deferred.
- [x] **Slice 4 — Restricted shell:** `shell_run` — allowlisted bare-name executables, no shell interpretation (metacharacters rejected), `requested_scope` contains cwd + every argument path, R2 approval per command, 32 KiB output cap, minimal env, SIGTERM→SIGKILL cancel; live-OS verified. The only command-string tool.
- [x] **Slice 5 — Git workflow tools:** `git_status`/`git_log`/`git_diff` (R0, structured) + `git_add`/`git_commit` (R1, self-verified via rev-parse), scoped repo cwd + add path args; `diff` redacted; live-OS verified in a real repo. Push/history ops deferred.
- [x] **Slice 6 — macOS app control:** `app_list` (R0), `app_launch`/`app_focus` (R1) via PyObjC `NSWorkspace`, scoped by `approved_apps`, state-probe self-verified; live-OS verified (real launch/focus, non-intrusive). AX *element* interaction (Accessibility TCC) deferred.
- [~] macOS adapters: app launch/focus (PyObjC) done; AX element interaction + AppleScript/JXA deferred (need TCC)
- [x] Filesystem adapter with approved-directory scoping
- [x] Restricted shell tool per TOOL_CONTRACTS §4
- [x] Git workflow tools (local ops; push deferred)
- [x] **Slice 7 — Browser adapter:** `browser_read` (R1) via headless Chromium/Playwright behind a swappable `BrowserAdapter`; domain allowlist enforced by the slice-1 scope enforcer (`requested_scope(domains=[host])`); web text `WEB_UNTRUSTED` + redacted; live-OS verified (real `example.com`, off-list refused). Playwright-Python in-daemon (MCP-swappable, see ADR-018); clicking/forms deferred.
- [x] **Slice 8 — Real planner behind the frozen PlannerAdapter:** `ClaudePlanner` — planning-only Anthropic Messages call (`claude-opus-4-8`, structured output), untrusted plan validated by schema/registry/policy/scope, never executes tools (ADR-019); injected client fully unit-tested. Default planner stays `mock`. **Live Anthropic call pending real-key verification.**
- [x] Desktop↔daemon session auth token
- [x] **Slice 9 — Views wired to real daemon state:** Permissions (live grants + revoke), Skills (live list + enable toggle; no seeds — empty until the engine ships), Settings (read-only real config) over `GET/PATCH /api/skills` + `GET /api/settings`.
- [ ] Voice: push-to-talk capture, whisper.cpp/faster-whisper STT, `say` TTS
- [~] Skill engine + Skills view wiring — **Skills view wired**; skill *engine* (execution) deferred
- [x] Permissions view wired to real grants/revocations

**THOTH cannot control the computer until Phase 3 lands and is verified.**

## Phase 4 — Operational capstone, skills and voice (IN PROGRESS)

Plan and per-slice audit: `docs/PHASE_4_GAP_REPORT.md`. Build order: foundations (2, 7, 8, 9) → adapters (3, 4, 5, 6) → live (1, 10) → hardening/gate (11, 12). Slices needing an API key, Accessibility TCC, or a microphone are built and unit-tested now, **labelled "pending live verification"** until that environment exists.

- [x] **Slice 2 — End-to-end correlation:** one `correlation_id` minted per task and threaded through plan, steps, tool invocations/results, verifications, approvals, and every audit event (indexed `audit_events.correlation_id`, migration 0003); desktop PlanView distinguishes proposed → approved → executed → verified per step and shows the correlation id.
- [x] **Slice 7 — Independent verification framework:** 12 verifiers (`FILE_EXISTS`, `FILE_CONTENT`, `PROCESS_RUNNING`, `PORT_LISTENING`, `HTTP_HEALTH`, `GIT_STATE`, `APPLICATION_RUNNING`, `ACCESSIBILITY_VALUE`, `BROWSER_URL`, `BROWSER_ELEMENT`, `EXIT_CODE`, `COMPOSITE`) probing real post-execution state via an injected `VerifierContext`; `verify_step` enforces the tool's declared strategy as the un-removable baseline and ANDs planner-declared checks on top; un-wired probes (AX without TCC, browser) report `available=False` and fail closed. AX/app/browser probe *wiring* lands with slices 3/4.
- [x] **Slice 8 — Bounded recovery:** recovery actions are now `retry | replan | escalate | fail`; limits enforced — ≤2 retries/step, ≤2 replans/task (each replan re-invokes the planning-only planner with failure context and the fresh plan re-enters policy review), recovery depth ≤3 consecutive failing episodes, and a hard ≤25 tool-executions/task cap in the orchestrator. Exhausted budgets end in the new terminal `FAILED_REQUIRES_USER` state (never a silent failure, never an unbounded loop); denials still fail immediately without touching budgets.
- [x] **Slice 9 — Tamper-evident audit hash chain:** every audit event carries `hash = sha256(prev_hash + task_id + correlation_id + seq + event_type + canonical(payload) + canonical(created_at))`; per-task chain, genesis prev_hash `""`. `AuditStore.verify_chain` recomputes from genesis and reports the first break (mutation, deletion/seq-gap, reorder) — exposed as `GET /api/tasks/{id}/audit/verify` returning a `ChainManifest`. The store still exposes no update/delete surface; the chain catches tampering done around it (direct DB edits, proven by tests).
- [x] **Slice 3 — Accessibility adapter + tools:** AXAdapter protocol (role+label addressing, never coordinates); RealAXAdapter over PyObjC AXUIElement gated by AXIsProcessTrusted (typed AXPermissionError without TCC — *element interaction pending live verification*); MockAXAdapter for tests; six tools (inspect/find/read/wait R0, set_value/perform_action R1, app-scoped, dry-run safe, set self-checks by re-read); dev-only AX test app with deterministic labels.
- [x] **Slice 4 — Browser interaction + safe form submission:** stateful BrowserSession (mock DOM + real Playwright, file:// fixture round-trip verified); nine tools — open/click/fill/select/download/screenshot (R1, domain+path scoped), find (R0), prepare_submission (R1, captures exact payload + single-use id), submit (R2, refuses unknown/consumed/stale submissions). Injection containment tested: hostile page text stays inert data.
- [x] **Slice 5 — Skill engine:** declarative parameterized templates expanded (planning-only) into plans that enter the NORMAL pipeline; typed inputs (missing/extra/unknown-placeholder rejected); risk copied verbatim — attempted R0-for-R2 downgrade still halts for approval (tested); POST /api/skills/{id}/run (404/409/422); five built-ins seeded idempotently.
- [x] **Slice 6 — Voice:** STTAdapter (mock default; faster-whisper impl *pending live verification — model + mic*); interruptible TTS over real /usr/bin/say (interrupt <200ms, new-speak-interrupts, LIVE verified via silent `say -o` AIFF render); /api/voice/{transcribe,task,say,interrupt}. Transcript isolation PROVEN: a voice transcript saying 'approve the pending action' creates a new task and leaves the pending approval untouched. Desktop PTT capture UI pending (mic).
- [x] **Slice 1 — Planner evaluation framework:** declarative eval harness (`evals/planner_eval.py`) scoring any PlannerAdapter against allowed-tool sets, step caps, risk ceilings and required tools; reports are redacted **by construction** (tool names + risk levels only, step inputs excluded) and written to `docs/evaluations/`. Proven offline: mock suite 5/5 PASS (`2026-07-13-planner-eval-mock.md`). LIVE_CASES against the real tool catalog via `--planner claude` are **pending live verification (needs ANTHROPIC_API_KEY)** — the CLI refuses cleanly without the key.
- [x] **Slice 10 — Five capstone workflows (scripted-planner runs REAL and verified):** create-project-note, continue-project, research-and-save (real https://example.com fetch), prepare-commit (real single-use approval exercised), launch-app (real TextEdit launch, independently probed via NSWorkspace). All five COMPLETED with independent final-state verification — see `docs/CAPSTONE_REPORT.md`. The same goals through the LIVE Claude planner (`--planner claude`) are **pending live verification (API key)**.
- [x] **Slice 11 — Hardening:** slice-7 diff went through a 12-agent adversarial review (3 reviewer lenses, every finding adversarially verified; 1 high + 6 low CONFIRMED, all fixed pre-merge — composite-any fail-open, EXIT_CODE self-certification, baseline-minimum enforcement, dispatcher fail-closed breadth). Slices 3–10 were reviewed inline after multi-agent review was blocked by session limits; two confirmed findings fixed with tests: browser_submit now refuses an approved `action_url` whose host differs from the PREPARED submission's action host (the approval must describe the real submission), and click/fill/select/prepare verify the `current_url` scope anchor against the session's ACTUAL page.
- [x] **Slice 12 — Final gate:** README/STATUS/MILESTONES/DECISIONS (ADR-020…026)/THREAT_MODEL (§6 Phase 3–4 surfaces)/TEST_PLAN/PRIVACY updated truthfully; CAPSTONE_REPORT.md committed. Full gate green: daemon 551, desktop 56, ruff/mypy/eslint/tsc/build clean, alembic single head. Maximum claim: “THOTH can safely execute and verify selected multi-step workflows across approved local applications, files, Git repositories and browser environments.” Live-planner runs, AX element interaction, and STT remain pending live verification (API key / TCC / mic).


## Phase 5 — Local-first embodiment (IN PROGRESS)

Plan/gap: `docs/PHASE_5_GAP_REPORT.md`. Gated: voice/proactivity do not start until the 5.0 (local inference) and 5.1 (hybrid routing) acceptance gates pass — both now pass.

- [x] **Slice 1 — Local inference abstraction:** provider-neutral `InferenceProvider` (deterministic / llama.cpp-family / MLX / optional-Anthropic-disabled-by-default); network-isolation guard (loopback-only); model registry with integrity hashes. Real qwen3:4b constrained-JSON round-trip verified through the loopback server.
- [x] **Slice 2 — Hardware + model benchmark:** real detection (Apple M4, 16 GB); measured suite (schema-valid/tool-selection/arg-extraction/risk-consistency/scope + timing) over qwen3:4b and qwen3:8b via Ollama; MLX recorded unavailable; default selected by measurement (qwen3:4b). `docs/LOCAL_MODEL_EVALUATION.md`.
- [x] **Slice 3 — Reflex/hybrid intent router:** REFLEX (deterministic, **no LLM** — asserted, incl. injection phrasings) / SKILL / PLANNER tiers; `POST /api/intent/route` classification.
- [x] **Slice 4 — Local constrained planner:** `LocalPlanner` + strict `PlanValidator` (unknown tool / bad args / risk downgrade / oversized / missing verifier / unsupported app rejected before risk review); no-cloud fallback ladder (skill → clarify → fail safe); real qwen3:4b plan cleared the validator live. `planner="local"` selectable.
- [x] **Phase 5.2 — persona:** immutable verified-fact composition; deterministic lifecycle templates; approval/refusal/failure never model-phrased; optional local summary behind factual/policy/target validation; deterministic fallback; display/spoken separation; live Qwen summary verified.
- [x] **Phase 5.3 — foreground and focus:** on-demand redacted foreground broker with bounded retention and no screenshot/AX-tree fields; authoritative per-tool focus policy enforced around `EXECUTING`; preservation/restoration independently checked and audited.
- [x] **Phase 5.3 — application/workspace context:** six immutable versioned profiles; unknown/forbidden/experimental fail closed; authoritative path/task workspace matcher with title/bundle hints only; real Code + THOTH path capstone verified.
- [x] **Phase 5.3 — operational dialogue:** task-isolated in-memory TTL state; authoritative artifact/workspace resolution; ambiguity/expiry fail safely; vague approval, scope expansion, cross-task leakage, and push-after-`no_push` blocked.
- [x] **Phase 5.3 — daemon/desktop integration:** authoritative task presentation API and WS sibling payload; runtime/foreground/workspace/focus/dialogue/stage status rendered in React; nine operational UI scenarios tested.
- [x] **Phase 5.3 — hardening/final gate:** model target/tool/risk directive rejection; foreground/workspace/profile/dialogue/focus adversarial coverage; 782 daemon + 65 desktop tests pass. The previously locked live focus-restoration test passed on the 2026-07-14 unlocked rerun.
- [~] **Phase 5.4 — Accessibility embodiment:** unlocked focus handoff, packaged unique-bundle test app, typed permission boundary, bounded untrusted snapshots, semantic resolver, ten narrow tools, independent verifiers, immutable profile rules, focus/cancellation ordering, desktop diagnostics, deterministic persona outcomes, resource ceilings, and adversarial coverage are complete. Real host packaging/identity and fail-closed permission evidence pass. Test-app/TextEdit UI capstones remain blocked because TCC is `not_determined`; the current rerun was also locked at loginwindow. No AX capability has been promoted from experimental. See `docs/PHASE_5_4_CAPSTONE.md`.
- [~] **Phase 5.5 — local voice and presence:** provider-neutral whisper.cpp STT, visible push-to-talk/partial/final/edit lifecycle, deterministic global Stop, local macOS/Piper TTS, native shortcut/menu/overlay/HUD, persona/dialogue integration, local runtime management, numeric latency metrics, and offline browser isolation are implemented and automated-test covered. Real Whisper candidate evaluation, microphone/global-shortcut capstones, 30 spoken commands, offline voice-to-action, and end-to-end memory/latency evidence remain open. See `docs/PHASE_5_5_CAPSTONE.md`.
