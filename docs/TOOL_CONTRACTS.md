# OmniMac Tool Contracts

Every tool registered with the tool registry MUST satisfy this contract. The registry rejects tools that don't; CI tests enforce it for every shipped tool.

## 1. Required contract fields (`ToolDefinition`)

| Field | Type | Requirement |
|---|---|---|
| `name` | str | Unique across the registry; `mock_` prefix mandatory for mocks |
| `description` | str | Human-readable; shown in approval drawer |
| `input_model` | Pydantic model | `extra="forbid"`; every argument typed; unknown/extra args rejected |
| `output_model` | Pydantic model | Typed result |
| `default_risk` | `RiskLevel` | R0–R3; the policy floor — effective risk is `max(default_risk, declared step risk)` |
| `timeout_s` | float | Hard execution timeout; exceeding it is a tool failure |
| `supports_cancellation` | bool + behavior | Cooperative cancellation; must stop promptly and report `cancelled` |
| `supports_dry_run` | bool + behavior | Dry-run must produce **no side effect** and return a preview |
| `verification` | `VerificationStrategy` | How the engine confirms the intended result (see §3) |
| `resource_scope` | `ResourceScope` | Permitted paths / domains / apps; executor enforces |
| `redaction_fields` | list[str] | Field names masked in audit/logs/WS beyond global secret patterns |
| unit tests | pytest | Valid input, invalid input, timeout, cancellation, dry-run, redaction |

No tool accepts arbitrary shell text except the dedicated restricted shell tool (§4).

## 2. Invocation lifecycle

```
PlanStep → PolicyDecision → (ApprovalRequest → ApprovalDecision)? → ToolInvocation
        → registry.validate(name, args) → executor (EXECUTING state only)
        → ToolResult → VerificationResult → audit
```

- The executor refuses to run unless the owning task is in `EXECUTING`.
- R2+ invocations require an `ApprovalDecision(approved=True)` bound to this `ToolInvocation.id`, unconsumed and unexpired.
- Results, including failures and timeouts, are always audited (post-redaction).

## 3. Verification strategies

| Strategy | Meaning | Example |
|---|---|---|
| `output_assertion` | Validate declared postconditions against typed tool output | mock tools, git status |
| `state_probe` | Run a read-only probe tool afterwards and compare | file exists after write |
| `none_readonly` | R0 reads may skip verification | list directory |

A step without a passing verification is not COMPLETED — it routes to RECOVERING or FAILED. "Command exited 0" is never sufficient by itself.

## 4. Restricted shell tool (Phase 3 — contract fixed now)

The only tool accepting a command string. It must:

- Require an approved working directory (from `WorkspaceProfile`).
- Enforce an executable **allowlist** (e.g. `git`, `ls`, `cat`, project runners) and a **denylist** (anything credential- or system-touching).
- Reject shell expansion/chaining where possible: `;`, `&&`, `||`, backticks, `$( )`, redirection outside the workspace, glob-based mass operations.
- Reject `sudo`, broad deletion (`rm -rf /`, `rm -rf ~`, wildcard roots), and access to credential locations (`~/.ssh`, `~/.aws`, `~/.config/gcloud`, Keychain files, `.env`).
- Enforce `timeout_s` and an output size cap (truncate + note).
- Redact secrets from captured output before storage.
- Record command, exit code, and duration in the audit trail.
- Support cooperative cancellation (SIGTERM → SIGKILL escalation).

## 5. Tool-selection order (router policy)

1. Official API or MCP integration
2. Browser DOM automation
3. Application CLI or restricted shell
4. macOS Accessibility element interaction
5. Screenshot + coordinate interaction — **forbidden when a structured interface exists**

## 6. Phase 2 mock tools

All mocks are clearly marked, side-effect-free (in-memory only), and exist to exercise the safety core:

| Tool | Risk | Purpose |
|---|---|---|
| `mock_read_file` | R0 | happy-path read; scope checks |
| `mock_list_dir` | R0 | read-only, `none_readonly` verification |
| `mock_open_app` | R1 | trusted-workspace auto-run behavior |
| `mock_edit_file` | R1 | dry-run + verification via output assertion |
| `mock_send_email` | R2 | approval enforcement; redaction of `body`/`recipient` |
| `mock_git_push` | R2 | approval enforcement |
| `mock_delete_dir` | R3 | blocked-by-default path |
| `mock_flaky` | R1 | fails N times then succeeds — recovery/retry tests |
| `mock_slow` | R0 | sleeps past timeout — timeout/cancellation tests |
