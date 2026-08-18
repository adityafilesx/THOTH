# Slice 8 — Real planner behind the frozen PlannerAdapter (design/spec)

**Date:** 2026-07-12 · **Phase:** 3 · **Status:** building (Stop-hook-driven)
**Verifiable here:** PARTIAL. Planner logic + validation + wiring are fully unit-tested (injected client). The **live Anthropic API call is NOT verifiable** — no API key in this environment. Labeled honestly.

## 1. The invariant that shapes this slice

The goal says "claude-agent-sdk planner." The `claude-agent-sdk` product is Claude Code as a
library — a **tool-executing** agent loop. Using it would violate **invariant 1: the planner NEVER
executes tools.** So OmniMac's planner does **not** run an agent loop. It makes a single **planning-only**
call to Claude (Anthropic Messages API, structured JSON output) that returns a typed `ExecutionPlan`
over the real tool catalog. The plan is **model output — untrusted** — and is validated against the
`ExecutionPlan` schema + the tool registry + the policy engine exactly as the mock planner's output
is, before any risk review or execution. Recorded as **ADR-019**.

## 2. Scope

- `ClaudePlanner(PlannerAdapter)` — same frozen `plan(task_id, goal) -> ExecutionPlan` contract; no
  contract change. Builds a tool-catalog system prompt from the registry, asks Claude for a JSON plan
  (structured output, `claude-opus-4-8`), maps it to `PlanStep`s, returns an `ExecutionPlan`.
- Injected `PlannerClient` protocol so the logic is unit-tested with a fake; the real
  `AnthropicPlannerClient` lazily imports `anthropic` and calls `messages.create` with
  `output_config.format` (JSON schema). Needs `ANTHROPIC_API_KEY` only when selected.
- Config switch `planner = "mock" | "claude"`; `app.py` selects. Default stays `mock` (offline, tested).
- `Orchestrator.submit` hardened: a planner that raises (network/parse/validation) fails the task
  cleanly instead of 500ing. Mock planner never raises → existing behavior unchanged.

**Non-goals:** streaming; running the sync API call off the event loop (noted follow-up); tool-use /
agent-loop planning (would violate invariant 1); verifying a live call (no key).

## 3. Components

| File | New? | Responsibility |
|---|---|---|
| `core/claude_planner.py` | new | `PlannerClient` protocol, `ClaudePlanner`, `AnthropicPlannerClient` (lazy `anthropic`), `PLAN_SCHEMA`, `build_system_prompt`. |
| `core/orchestrator.py` | edit | `submit` catches planner errors → task FAILED + audit. |
| `config.py` | already has `planner`; `app.py` | select `ClaudePlanner` when `planner=="claude"`. |
| `pyproject.toml` | edit | `anthropic>=0.40` (lazy import). |
| docs | edit | ADR-019, STATUS, MILESTONES. |

## 4. Behavior

- `build_system_prompt(registry)`: lists every registered tool — `name`, `default_risk`, `description`
  — and the rules: use ONLY listed tools; never invent a tool or arguments; set `declared_risk` from
  the tool's stated risk; keep steps minimal; **do not** attempt destructive/off-scope actions.
- `PLAN_SCHEMA`: `{summary: str, steps: [{title, tool_name, arguments: object, declared_risk: enum
  R0|R1|R2|R3}]}`, `additionalProperties:false`, `required` set — the structured-output constraints
  the API supports.
- `ClaudePlanner.plan`: `raw = client.complete_plan(system, goal, PLAN_SCHEMA)`; map each step (index
  is authoritative, from enumeration — not model-supplied), coerce `declared_risk` via `RiskLevel(...)`
  (invalid → `ValueError` → caught by submit); build `ExecutionPlan` (≥1 step required; empty → error).
  **It calls the client and constructs a plan — it never touches the registry executor.**
- `AnthropicPlannerClient.complete_plan`: lazy `import anthropic`; `Anthropic()` (reads
  `ANTHROPIC_API_KEY`); `messages.create(model="claude-opus-4-8", max_tokens=4096, system=…,
  output_config={"format":{"type":"json_schema","schema":schema}}, messages=[{user: goal}])`;
  `json.loads` the first text block. Sync (frozen contract is sync) — blocking the loop on the network
  call is a documented follow-up (offload to a thread).

## 5. Untrusted-output containment (unchanged safety core does the work)

The plan flows through the **existing** pipeline: schema-validated, then the orchestrator rejects any
`unknown tool` at PLANNING (already tested), the policy engine classifies each step from typed fields
(R3→FAILED, R2→approval), the scope enforcer gates every path/domain/app, and nothing executes outside
EXECUTING. A malicious or hallucinated plan cannot expand scope, invent a tool, or downgrade risk — the
planner is just another untrusted input to the same gates. The planner itself performs **zero** tool
execution.

## 6. Testing / verification

- **Unit (FakePlannerClient):** a canned plan → correct `ExecutionPlan` (steps, tool_name, risk,
  contiguous indexes); `build_system_prompt` lists real tools (`fs_read_file`, `shell_run`, `git_status`,
  `app_launch`, `browser_read`); empty/invalid-risk plan → `ValueError`.
- **Orchestrator integration (real safety core, fake client):** a plan naming an **unknown tool** →
  task FAILED at PLANNING (proves untrusted-output rejection); a valid in-scope R0 plan (e.g. `fs_stat`)
  → COMPLETED, and the fake client's `complete_plan` was called exactly once (proves the planner ran and
  produced a real plan without executing anything itself); a planner that **raises** → task FAILED
  cleanly, not a crash.
- **Live (guarded):** a smoke script that runs a real plan only if `ANTHROPIC_API_KEY` is set; otherwise
  prints `SKIPPED (no ANTHROPIC_API_KEY)`. STATUS records the live path as **implemented, pending
  real-API verification**.
- **Regression:** full suite green; `planner` defaults to `mock`.

## 7. Honesty

The planner is implemented behind the frozen adapter and its logic + untrusted-output containment are
verified. The live Anthropic call is **not** verified here (no key). Even with the real planner enabled,
OmniMac only *plans* over tools that are still individually scope-/approval-gated — this is the capstone
that makes goal→plan autonomous, but every action remains gated by the safety core, and slices 6–8's
adapters that couldn't be OS-verified stay labeled as such.

## 8. ADR-019

Planning-only Claude call (Messages API, structured output, `claude-opus-4-8`) behind the frozen
`PlannerAdapter` — **not** the tool-executing claude-agent-sdk agent loop, which would violate "planner
never executes tools." Output is untrusted and validated by the existing schema/registry/policy/scope
gates. Injected `PlannerClient` for testability; `anthropic` lazily imported; default planner stays
`mock`. Sync call per the frozen contract (threadpool offload is a noted follow-up).
