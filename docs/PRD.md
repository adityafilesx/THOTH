# THOTH — Product Requirements Document

## 1. Product definition

THOTH is a local-first, voice-enabled macOS computer operator. It converts a spoken or typed goal into a structured, risk-classified execution plan, obtains approval for sensitive steps, executes through the safest available tool, verifies each result, recovers from bounded failures, and records a complete audit trail. It stops instantly when interrupted.

THOTH is **not** a chatbot, note-taking application, generic second brain, or simple voice-command launcher.

## 2. Goals

1. Understand a spoken or typed goal.
2. Create a structured execution plan.
3. Classify every action by risk (R0–R3).
4. Request approval immediately before sensitive actions.
5. Execute through the safest available tool.
6. Verify that each action achieved its intended result.
7. Recover from limited failures.
8. Record a complete audit trail.
9. Stop instantly when interrupted.

## 3. Non-goals (explicitly excluded)

- Autonomous job submissions, payments, or trading.
- System administration (`sudo`, security settings, production deployment).
- Always-on recording or wake-word listening (push-to-talk only initially).
- Windows or Linux support during initial phases.
- Cloud-hosted processing where local processing is practical.

## 4. Product principles (priority order)

1. Safety over autonomy
2. Reliability over feature count
3. Structured tools over screen coordinates
4. Verification over assumption
5. Local processing over cloud processing where practical
6. Explicit user control over hidden background behavior
7. Typed contracts over free-form agent output
8. Small independently testable modules over a monolithic agent
9. No destructive action without explicit authorization
10. No external side effect based only on previously granted general permission

## 5. Target platform & capabilities

macOS first. The application must eventually support: push-to-talk voice commands; text commands; application launching and focusing; approved filesystem access; restricted terminal commands; Git workflows; browser research and form completion; workspace restoration; daily planning; draft creation; and explicit approval for sending, uploading, submitting, or publishing.

## 6. Initial workflows

1. **Continue a configured software project** — restore workspace, inspect repo state, start dev services, summarize next actions.
2. **Research a topic** — browse approved domains, save a cited Markdown report locally.
3. **Prepare a daily plan** — read configured sources (calendar, notes), produce a plan draft.
4. **Draft an email without sending it** — sending is a separate R2 approval.
5. **Open applications, files, folders, and browser pages.**
6. **Inspect repository state and start local development services.**

## 7. Risk policy (product-level)

| Level | Class | Examples | Behavior |
|---|---|---|---|
| R0 | Read-only | read approved file, list directory, git status, read webpage/calendar | Auto inside approved boundaries |
| R1 | Reversible local | open app, start local service, create draft, edit files in approved repo | Auto only in trusted workspace |
| R2 | External side effect | send email, submit form, create calendar event, upload, git push, publish | Explicit approval immediately before execution |
| R3 | Destructive/sensitive | sudo, broad deletion, security settings, financial, auth changes, prod deploy, disabling safety engine | Blocked by default |

No planner or tool may downgrade its own risk level.

## 8. User interface

Seven desktop views. Refined dark interface inspired by scientific command systems; readability over visual effects.

1. **Command center** — voice + text input; current response; listening/planning/approval/execution states; global Stop button.
2. **Execution plan** — ordered steps, tool per step, risk indicator, current step, verification status.
3. **Approval drawer** — exact proposed action; target app/file/domain/recipient; data being sent; reason approval is required; Approve once / Deny / Modify action.
4. **Activity timeline** — every task and tool event with duration, result, failure details, generated artifacts.
5. **Permissions** — approved applications, workspace directories, browser domains; revocation controls.
6. **Skills** — installed skills, workflow preview, input configuration, enable/disable.
7. **Settings** — model, voice, privacy, retention, trusted workspaces.

## 9. Success criteria

- 100% of R2 executions preceded by an explicit, single-use, invocation-bound approval.
- 0 tool executions outside the `EXECUTING` state (enforced + tested).
- Every state change auditable; audit trail replays task history losslessly.
- Global Stop cancels an in-flight task within one tool-timeout tick.
- All safety-core behavior covered by automated tests (see TEST_PLAN.md).

## 10. Phasing

- **Phase 0** — engineering docs, repo configuration, Claude Code agents/rules/hooks.
- **Phase 1** — desktop shell, daemon, health, WS events, SQLite + migrations, structured logging, command-center + plan + timeline UI on mock data.
- **Phase 2** — contracts, state machine, risk engine, approvals, tool registry + mock tools, verification, recovery, audit store, task API/WS.
- **Phase 3+** — real macOS adapters (PyObjC/AX), browser automation (Playwright MCP), restricted shell, voice pipeline, skill engine. **Until Phase 3 integration and verification are complete, THOTH cannot control the computer.**
