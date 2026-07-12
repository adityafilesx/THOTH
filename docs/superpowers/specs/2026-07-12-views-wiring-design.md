# Slice 9 — Permissions/Skills/Settings views wired to real daemon state (design/spec)

**Date:** 2026-07-12 · **Phase:** 3 · **Status:** approved (user selected "continue verifiable slices"), pre-plan
**Depends on:** slices 1–2 (permissions API + auth), merged.

## 1. Problem

Permissions, Skills, and Settings render static fixtures labeled "mock data". The daemon now has a
real permissions API (slice 1) but no skills/settings API. Wire all three views to real daemon
state; remove the mock badges; add the two missing (small) daemon APIs.

## 2. Goals / non-goals

**Goals**
- Daemon: `GET /api/skills`, `PATCH /api/skills/{skill_id}` (enable/disable) over the existing
  `skills` table via a `SkillStore`; `GET /api/settings` returning real, safe daemon values.
- Desktop: all three views driven by TanStack Query over the (auth'd) API client; Permissions
  Revoke really revokes; Skills toggle really persists; honest empty state for skills.
- Tests: daemon API tests; vitest view tests against mocked fetch; live daemon check; build green.

**Non-goals**
- Skill *engine* / execution (later Phase 3) — the view lists whatever real `SkillDefinition`s
  exist; **no seeded fixtures** (seeded examples would be mock data dressed as real; violates the
  no-overclaim rule).
- Settings *editing* (needs per-key validation + daemon restart semantics; deferred).
- Add-grant / add-workspace UI (API exists; UI later).
- Voice UI.

## 3. Daemon components

| File | New? | Responsibility |
|---|---|---|
| `storage/skills.py` | new | `SkillStore(session_factory)`: `list_skills() -> list[SkillDefinition]`, `set_enabled(skill_id, enabled) -> bool` (False if unknown). Rows ↔ `SkillDefinition` (definition_json). |
| `api/skills.py` | new | `GET /api/skills` → list; `PATCH /api/skills/{id}` body `{enabled: bool}` (`extra="forbid"`) → updated definition or 404. Audit `skill.toggled` under task_id `"system"`. |
| `api/settings.py` | new | `GET /api/settings` → `{version, planner, approval_ttl_seconds, max_retries_per_step, max_retries_per_task, trusted_workspaces}`. Read-only; **never** returns token/paths of secrets. |
| `app.py` | edit | build `SkillStore`, expose on `app.state.skills`; register the two routers. |

All under the slice-2 bearer middleware automatically (not in `_OPEN_PATHS`).

## 4. Desktop components

| File | Change |
|---|---|
| `lib/api.ts` | add `permissions()`, `revokeGrant(id)`, `skills()`, `setSkillEnabled(id, enabled)`, `settings()` + result types. |
| `views/Permissions.tsx` | Query `["permissions"]`; render real workspaces (roots) + grants grouped by kind (path/domain/app); Revoke → mutation → invalidate. Loading/error states. Badge: remove "mock data" (show "live"). |
| `views/Skills.tsx` | Query `["skills"]`; real rows; Switch → `setSkillEnabled` mutation → invalidate; empty state: "No skills installed. The skill engine arrives later in Phase 3 — every skill run will still pass risk review and approvals." Remove badge. |
| `views/Settings.tsx` | Query `["settings"]`; real values into the same read-only layout (planner, retention placeholders removed if not real — show only real config: planner, approval TTL, retry budgets, trusted workspaces, daemon version). Remove badge. |
| `views/views.test.tsx` | update: views render real data from mocked fetch; revoke/toggle fire the right calls; skills empty state. |

Retention fields ("history 90d / logs 14d") are **not** real daemon config — remove them rather
than display invented values.

## 5. Testing / verification

- Daemon: `GET /api/skills` empty → `[]`; insert via store → listed; PATCH toggles + persists +
  404 unknown + 422 extra field; `GET /api/settings` shape + no secret keys; all 401 without token.
- Desktop: vitest with stubbed fetch (token via env stub, established pattern): permissions render +
  revoke calls DELETE; skills empty state + toggle calls PATCH; settings renders real values.
- Live: daemon up → curl the three GETs with token (200, real values), without (401); `pnpm build`.
- Full gates both sides.

## 6. ADR

**ADR-016:** views wired to real state; skills listed from SQLite with enable toggle only (no
engine, no seeds — empty is honest); settings read-only real config; retention placeholders removed
as not-real. Editing + skill engine deferred.
