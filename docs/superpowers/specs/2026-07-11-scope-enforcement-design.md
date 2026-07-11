# Slice 1 — Scope enforcement + permission store (design/spec)

**Date:** 2026-07-11 · **Phase:** 3 · **Status:** approved design, pre-plan
**Author:** THOTH engineering (paired) · **Depends on:** Phase 2 safety core (complete)
**Blocks:** every real adapter (filesystem, shell, git, app, browser), Permissions-view wiring (slice 9)

## 1. Context & problem

Phase 2 shipped a complete, tested safety core over **mock tools only**. Two facts make this
slice the mandatory first step of Phase 3:

1. **`resource_scope` is declared but never enforced.** `ToolDefinition` carries a
   `resource_scope: ResourceScope` and `docs/TOOL_CONTRACTS.md §1` states *"the executor
   enforces"* it, but there is **no enforcement code** in `tools/registry.py` or the
   orchestrator. It never mattered because every mock is in-memory. The moment a real tool
   touches disk, an unenforced scope is a direct path to threat **T3 (tool misuse & scope
   creep)** and **T5 (secret leakage)**.
2. **Grants are static.** The single `WorkspaceProfile` is built once in `app.py` from
   `cfg.trusted_workspaces`. There is no persistent, user-driven store of what THOTH may
   touch, and no API for the Permissions view to read or mutate.

This slice builds the enforcement layer and its backing store. **It adds no real file, shell,
or app I/O** — that is slice 3+. Success is: an out-of-scope target is refused deterministically,
before execution, and provably never reaches a tool; and grants live in SQLite behind a typed
API driven only by trusted user action.

## 2. Goals / non-goals

**Goals**
- Central, reusable path safety primitives (expansion, realpath, containment, denylist).
- A stateless `ScopeEnforcer` that decides allow/deny from typed inputs only.
- Enforcement at two points (defense in depth): orchestrator pre-EXECUTING (primary) and
  `registry.execute` (backstop).
- Persistent `WorkspaceProfile` + `PermissionGrant` store and a typed permissions API.
- Full TDD coverage of allowed **and** rejected paths.
- Preserve every existing invariant and keep the current 256 daemon + 42 desktop tests green.

**Non-goals (this slice)**
- Desktop↔daemon auth token (slice 2).
- Any real filesystem/shell/app/browser I/O (slice 3+).
- Permissions **view** UI wiring (slice 9) — this slice ships only the API it will consume.
- Subdomain / bundle-id matching nuance (domains & apps are exact-match here; revisited in
  the browser and app slices).

## 3. Components (new & touched)

| File | New? | Responsibility |
|---|---|---|
| `security/paths.py` | new | `expand_and_resolve(p) -> Path` (`~` + `realpath`, symlink-safe, `strict=False`); `is_within(path, root) -> bool` (containment after resolve); `is_denied_path(path) -> bool`; `DENY_DIRS`, `DENY_NAME_GLOBS`. |
| `core/scope.py` | new | `ScopeViolation(Exception)`; `ScopeEnforcer.check(requested: ResourceScope, allowed: ResourceScope) -> None` (raises `ScopeViolation` on the first offending target). Pure/stateless. |
| `storage/permissions.py` | new | `PermissionStore(session_factory)` mirroring `AuditStore`: `list_workspaces`, `upsert_workspace`, `list_grants`, `add_grant`, `revoke_grant`, `effective_scope(workspace_id) -> ResourceScope`. |
| `api/permissions.py` | new | REST router (see §7). |
| `alembic/versions/0002_*.py` | new | `workspace_profiles` + `permission_grants` tables. |
| `schemas/contracts.py` | edit | add `PermissionKind` (Literal `path|domain|app`) + `PermissionGrant`; export both. |
| `schemas/__init__.py` | edit | export the new contracts. |
| `storage/models.py` | edit | add `WorkspaceRow`, `PermissionGrantRow`. |
| `tools/base.py` | edit | add `requested_scope(self, args) -> ResourceScope` (default: empty). |
| `tools/registry.py` | edit | backstop: `execute(invocation, allowed_scope=None)` runs the enforcer before `tool.run`. |
| `core/orchestrator.py` | edit | primary gate pre-EXECUTING; resolve effective scope per step via injected async `scope_provider`; thread it to `guarded_execute`. |
| `app.py` | edit | build `PermissionStore`, seed default workspace from config, inject enforcer + store. |
| `docs/DECISIONS.md` | edit | ADR: `requested_scope` + central `ScopeEnforcer` completes the "executor enforces scope" contract. |

## 4. Data model

**Contracts (`schemas/contracts.py`, additive — nothing removed or renamed):**

```python
PermissionKind = Literal["path", "domain", "app"]

class PermissionGrant(StrictModel):
    id: str = Field(default_factory=_new_id)
    workspace_id: str
    kind: PermissionKind
    value: str
    granted_at: datetime = Field(default_factory=_utcnow)
    revoked: bool = False
```

`WorkspaceProfile` already exists (`id, name, root_path, trusted, approved_domains,
approved_apps`) and is reused unchanged.

**Tables (`storage/models.py`, style matches existing rows — `String(36)` ids, JSON, UTC):**
- `WorkspaceRow(id, name, root_path, trusted, approved_domains_json, approved_apps_json, created_at)`
- `PermissionGrantRow(id, workspace_id[index], kind, value, revoked[default False], granted_at)`

`init_schema` (`create_all`) and Alembic migration `0002` are kept in parity — both must
produce these two tables. Secrets are never stored (values are paths/domains/app names).

## 5. Enforcement flow — defense in depth

### 5.1 Tool declares what it will touch
`ToolDefinition` gains:

```python
def requested_scope(self, args: Any) -> ResourceScope:
    return ResourceScope()  # default: touches nothing
```

Mocks do not override it ⇒ they request an empty scope ⇒ nothing to check ⇒ they remain
allowed. **This is why the existing 256 tests stay green.** Real tools override it, e.g. a
read tool returns `ResourceScope(paths=[args.path])`.

### 5.2 Effective (allowed) scope
`PermissionStore.effective_scope(workspace_id)` returns:
- `paths` = `[workspace.root_path]` + values of active (`revoked=False`) `kind="path"` grants
- `domains` = `workspace.approved_domains` + active `kind="domain"` grants
- `apps` = `workspace.approved_apps` + active `kind="app"` grants

Only the permissions API (trusted, §7) can add grants. **Untrusted content can never widen
this** — it has no path to the store. This upholds the injection-guard invariant.

### 5.3 `ScopeEnforcer.check(requested, allowed)`
For each requested target:
- **path**: `rp = expand_and_resolve(value)`. Deny if `is_denied_path(rp)`. Else require
  `any(is_within(rp, expand_and_resolve(root)) for root in allowed.paths)`. For write targets
  the tool declares the target path; containment is checked on the resolved path and its
  resolved parent (no creation through a symlinked parent).
- **domain**: require exact (case-insensitive) membership in `allowed.domains`.
- **app**: require exact membership in `allowed.apps`.
First offending target raises `ScopeViolation(kind, value, reason)`. Inputs are all typed
values from trusted sources (plan args + store) — no free text reaches the decision.

### 5.4 Primary gate — orchestrator, pre-EXECUTING
In `_execute_step`, **after** policy has allowed the step and **before** entering `EXECUTING`:
parse the step arguments (`tool.parse_arguments(invocation)`; a `ValidationError` here fails
the step pre-exec), then call the enforcer with `tool.requested_scope(parsed_args)` vs the
**current** effective scope. On `ScopeViolation`:
- audit `scope.denied` `{step_id, tool, kind, value, reason}`
- `_fail(f"step '{step.title}' blocked by scope: …")` ⇒ task **FAILED**, **never enters
  EXECUTING**, retry budget **untouched** (identical shape to a policy/approval denial;
  routed like `recovery.on_denied`).

Effective scope is resolved **fresh at each step gate** via an injected async
`scope_provider() -> ResourceScope` (wired in `app.py` to
`lambda: store.effective_scope(workspace_id)`), so a revocation made through the API while a
task runs takes effect immediately — honoring the Permissions view's "revoking takes effect
immediately" promise. The runner depends on the callable, not on the store type. The same
resolved snapshot is threaded to the backstop (§5.5) for that invocation.

### 5.5 Backstop — `registry.execute`
Signature becomes `execute(invocation, allowed_scope: ResourceScope | None = None)`. Before
`tool.run`, run the enforcer with `tool.requested_scope(args)` vs `allowed_scope` (None ⇒
treated as empty scope). On `ScopeViolation` return
`ToolResult(ok=False, error="scope violation: …")` — a typed, **non-retryable** failure.
`guarded_execute` and the orchestrator thread the step's freshly-resolved effective scope
(§5.4) through. Result: even
a direct `registry.execute` call cannot run a tool against an out-of-scope target. Mocks
request nothing, so `None`/empty scope leaves them unaffected and existing tests pass.

## 6. Denylist (blocked even inside an approved root)

`DENY_DIRS` (deny if resolved path is within any): `~/.ssh`, `~/.aws`, `~/.config/gcloud`,
`~/Library/Keychains`, `~/Library/Keychain`.
`DENY_NAME_GLOBS` (deny if basename matches): `.env`, `.env.*`, `id_rsa`, `id_dsa`,
`id_ecdsa`, `id_ed25519`, `*.pem`, `.netrc`.
Source: `docs/TOOL_CONTRACTS.md §4` + threat **T5**. Denylist wins over any grant.

## 7. Permissions API (`api/permissions.py`)

| Method / path | Body | Effect |
|---|---|---|
| `GET /api/permissions` | — | `{ "workspaces": [...], "grants": [...] }`, redacted |
| `POST /api/permissions/grants` | `{workspace_id, kind, value}` (`extra="forbid"`) | validate → `add_grant` → audit `permission.granted` |
| `DELETE /api/permissions/grants/{id}` | — | `revoke_grant` → audit `permission.revoked` (404 if unknown) |
| `GET /api/workspaces` | — | list workspace profiles |
| `POST /api/workspaces` | `WorkspaceProfile` fields | `upsert_workspace` → audit `workspace.upserted` |

- All bodies are `extra="forbid"` Pydantic models; unknown fields rejected.
- Grant/revoke/workspace events are appended to the audit store under a reserved
  `task_id = "system"`, preserving the single append-only log with per-key monotonic `seq`.
- These are trusted, user-initiated endpoints; slice 2 (auth token) will additionally gate
  them behind the session bearer.

## 8. Wiring (`app.py`)

- Build `PermissionStore(session_factory)`; on startup, seed a default `WorkspaceProfile`
  (name `"default"`, `root_path`/`trusted` from `cfg.trusted_workspaces`) if none exists.
- Construct a `ScopeEnforcer` (stateless) and inject it into the `Orchestrator` together with
  an async `scope_provider` = `lambda: store.effective_scope(default_workspace_id)`. The
  runner resolves scope per step from this callable (§5.4) and threads it to the executor.
- Register `api/permissions.py` router; expose `PermissionStore` on `app.state`.

## 9. Error handling & audit

| Situation | Result |
|---|---|
| Requested path outside all roots | `ScopeViolation` → FAILED pre-exec / non-retryable result |
| Requested path in denylist | same, reason `"denied path"` |
| Requested domain/app not granted | same |
| Grant with unknown `kind` / extra field | HTTP 422 (Pydantic) |
| Revoke unknown grant id | HTTP 404 |
| Enforcer sees empty requested scope | allow (mocks) |

New audit event types: `scope.denied`, `permission.granted`, `permission.revoked`,
`workspace.upserted`. All redacted before write (path/domain/app values are not secrets, but
redaction runs unconditionally).

## 10. Testing strategy (TDD — write the failing test first)

- **`security/paths.py`**: `~` expansion; `..` traversal collapses & is rejected when escaping;
  symlink inside root pointing outside ⇒ `is_within` False; denylist dirs & name globs hit;
  containment true/false; non-existent write target resolves via parent.
- **`core/scope.py`**: in-scope path/domain/app allowed; out-of-scope each denied; denied path
  *inside* an approved root still denied; empty requested scope always allowed; first offender
  reported.
- **`storage/permissions.py`**: add/list/revoke grant; `effective_scope` unions workspace +
  active grants and excludes revoked; persists across a fresh store on the same DB; upsert
  workspace.
- **`api/permissions.py`**: GET shape; POST grant happy + `extra="forbid"` rejection + unknown
  `kind`; DELETE happy + 404; audit event emitted per mutation; redaction applied.
- **`core/orchestrator` integration**: a plan step whose tool requests an out-of-scope path
  ⇒ task FAILED, `scope.denied` audited, machine **never** reached EXECUTING, tool side-effect
  counter unchanged; an in-scope step proceeds normally.
- **`registry` backstop**: `execute(invocation, allowed_scope=<restrictive>)` on a scope-
  requesting stub tool ⇒ `ok=False`, non-retryable; mocks with `None` scope ⇒ unaffected.
- **Regression**: full existing suite stays green.

## 11. Invariants preserved (re-verified in tests)

No execution outside `EXECUTING`; no risk downgrade; approvals unchanged; append-only audit
(no update/delete surface added); redaction at every boundary; untrusted content cannot widen
scope. `docs/STATUS.md` / `docs/MILESTONES.md` updated truthfully; no capability overclaim
(this slice ships **no** real I/O).

## 12. ADR

Record in `docs/DECISIONS.md`: *"`ToolDefinition.requested_scope` + a central stateless
`ScopeEnforcer`, invoked at the orchestrator pre-EXECUTING gate and again in
`registry.execute`, implement the previously-unenforced 'executor enforces `resource_scope`'
clause of TOOL_CONTRACTS §1. Chosen over per-tool ad-hoc checks (un-auditable, forgettable)
and over enforcement only in the executor (misses fail-fast before EXECUTING)."*
