# Views Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Wire Permissions/Skills/Settings views to real daemon state; add `GET/PATCH /api/skills` + `GET /api/settings`.

**Architecture:** `SkillStore` over the existing `skills` table; two thin routers under the bearer middleware; desktop views use TanStack Query over the auth'd api client; real revoke/toggle mutations. No skill seeds (empty is honest); no settings editing.

**Tech Stack:** FastAPI/Pydantic v2/SQLAlchemy async; React 18/TanStack Query/vitest.

## Global Constraints
- mypy strict + ruff clean; tsc + eslint clean. `extra="forbid"`.
- No mock/seed data presented as real. Existing 365 daemon + 46 desktop tests stay green.
- Branch `phase-3/views-wiring`. Commit trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No push.

## File Structure
| File | C/M | Responsibility |
|---|---|---|
| `apps/daemon/src/thoth_daemon/storage/skills.py` | C | `SkillStore`. |
| `apps/daemon/src/thoth_daemon/api/skills.py` | C | skills router. |
| `apps/daemon/src/thoth_daemon/api/settings.py` | C | settings router. |
| `apps/daemon/src/thoth_daemon/app.py` | M | build store, register routers. |
| `apps/desktop/src/lib/api.ts` | M | new client methods + types. |
| `apps/desktop/src/views/{Permissions,Skills,Settings}.tsx` | M | real data. |
| `apps/desktop/src/views/views.test.tsx` | M | updated tests. |
| docs | M | ADR-016, STATUS, MILESTONES. |

Tests: `tests/api/test_skills_api.py`, `test_settings_api.py`.

---

### Task 1: `SkillStore` + skills API

**Files:** Create `storage/skills.py`, `api/skills.py`; Test `tests/api/test_skills_api.py`.

**Interfaces:** `SkillStore(session_factory)`: `async list_skills() -> list[SkillDefinition]`, `async set_enabled(skill_id, enabled) -> SkillDefinition | None`, `async add_skill(SkillDefinition)` (test helper/seed-free API). Routes `GET /api/skills`, `PATCH /api/skills/{id}`.

- [ ] **Step 1: Failing test**

```python
# apps/daemon/tests/api/test_skills_api.py
from httpx import AsyncClient

from thoth_daemon.schemas import SkillDefinition
from thoth_daemon.storage.skills import SkillStore


async def test_skills_empty_by_default(client: AsyncClient) -> None:
    r = await client.get("/api/skills")
    assert r.status_code == 200 and r.json() == []


async def test_skills_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/skills", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


async def test_patch_toggles_and_persists(client: AsyncClient, app) -> None:
    store: SkillStore = app.state.skills
    sk = SkillDefinition(name="demo", description="d", workflow=["fs_stat"], inputs=[], enabled=True)
    await store.add_skill(sk)

    listed = (await client.get("/api/skills")).json()
    assert len(listed) == 1 and listed[0]["enabled"] is True

    r = await client.patch(f"/api/skills/{sk.id}", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert (await client.get("/api/skills")).json()[0]["enabled"] is False


async def test_patch_unknown_404(client: AsyncClient) -> None:
    r = await client.patch("/api/skills/nope", json={"enabled": False})
    assert r.status_code == 404


async def test_patch_extra_field_422(client: AsyncClient, app) -> None:
    store: SkillStore = app.state.skills
    sk = SkillDefinition(name="d2", description="d", workflow=[], inputs=[], enabled=True)
    await store.add_skill(sk)
    r = await client.patch(f"/api/skills/{sk.id}", json={"enabled": False, "x": 1})
    assert r.status_code == 422
```

- [ ] **Step 2: Run → fails.**

- [ ] **Step 3: Implement `storage/skills.py`**

```python
# apps/daemon/src/thoth_daemon/storage/skills.py
"""Skill store over the `skills` table. Lists installed SkillDefinitions and
toggles their enabled flag. No seed data — an empty store is the honest state
until the skill engine ships."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from thoth_daemon.schemas import SkillDefinition
from thoth_daemon.storage.models import SkillRow


class SkillStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_skills(self) -> list[SkillDefinition]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(SkillRow))).scalars().all()
            return [self._to_def(r) for r in rows]

    async def add_skill(self, skill: SkillDefinition) -> SkillDefinition:
        async with self._session_factory() as session:
            session.add(
                SkillRow(
                    id=skill.id,
                    name=skill.name,
                    definition_json=skill.model_dump(mode="json"),
                    enabled=skill.enabled,
                )
            )
            await session.commit()
            return skill

    async def set_enabled(self, skill_id: str, enabled: bool) -> SkillDefinition | None:
        async with self._session_factory() as session:
            row = await session.get(SkillRow, skill_id)
            if row is None:
                return None
            row.enabled = enabled
            data = dict(row.definition_json)
            data["enabled"] = enabled
            row.definition_json = data
            await session.commit()
            return SkillDefinition.model_validate(data)

    @staticmethod
    def _to_def(row: SkillRow) -> SkillDefinition:
        return SkillDefinition.model_validate(row.definition_json)
```

- [ ] **Step 4: Implement `api/skills.py`**

```python
# apps/daemon/src/thoth_daemon/api/skills.py
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.storage.skills import SkillStore

router = APIRouter()
SYSTEM_TASK_ID = "system"


class SkillPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


def _skills(request: Request) -> SkillStore:
    return cast(SkillStore, request.app.state.skills)


@router.get("/api/skills")
async def list_skills(request: Request) -> list[dict[str, Any]]:
    return [s.model_dump(mode="json") for s in await _skills(request).list_skills()]


@router.patch("/api/skills/{skill_id}")
async def patch_skill(skill_id: str, body: SkillPatch, request: Request) -> dict[str, Any]:
    updated = await _skills(request).set_enabled(skill_id, body.enabled)
    if updated is None:
        raise HTTPException(status_code=404, detail="skill not found")
    audit = cast(AuditStore, request.app.state.audit)
    await audit.append(SYSTEM_TASK_ID, "skill.toggled", {"skill_id": skill_id, "enabled": body.enabled})
    return updated.model_dump(mode="json")
```

- [ ] **Step 5: Wire `app.py`** — after permissions store:
```python
        from thoth_daemon.storage.skills import SkillStore  # or top import
        app.state.skills = SkillStore(session_factory)
```
and `app.include_router(skills.router)` + import `skills`.

- [ ] **Step 6: Run → pass. Commit** `feat(api): SkillStore + GET/PATCH /api/skills (no seed data)`

---

### Task 2: settings API

**Files:** Create `api/settings.py`; modify `app.py`; Test `tests/api/test_settings_api.py`.

- [ ] **Step 1: Failing test**

```python
# apps/daemon/tests/api/test_settings_api.py
from httpx import AsyncClient


async def test_settings_shape(client: AsyncClient) -> None:
    r = await client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    for key in ("version", "planner", "approval_ttl_seconds", "max_retries_per_step",
                "max_retries_per_task", "trusted_workspaces"):
        assert key in body
    # no secret material
    assert "session_token" not in body and "token" not in body


async def test_settings_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/settings", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run → fails.**

- [ ] **Step 3: Implement `api/settings.py`**

```python
# apps/daemon/src/thoth_daemon/api/settings.py
from typing import Any, cast

from fastapi import APIRouter, Request

import thoth_daemon
from thoth_daemon.config import Settings

router = APIRouter()


@router.get("/api/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    cfg = cast(Settings, request.app.state.settings)
    return {
        "version": thoth_daemon.__version__,
        "planner": cfg.planner,
        "approval_ttl_seconds": cfg.approval_ttl_seconds,
        "max_retries_per_step": cfg.max_retries_per_step,
        "max_retries_per_task": cfg.max_retries_per_task,
        "trusted_workspaces": cfg.trusted_workspaces,
    }
```

- [ ] **Step 4: Wire `app.py`** — `app.include_router(settings.router)` + import. (`app.state.settings = cfg` already set.)

- [ ] **Step 5: Run → pass. Commit** `feat(api): read-only GET /api/settings`

---

### Task 3: desktop api client methods

**Files:** Modify `apps/desktop/src/lib/api.ts`.

- [ ] **Step 1:** Add types + methods (no dedicated test; exercised by view tests in Task 4):

```ts
export interface PermissionsResponse {
  workspaces: { id: string; name: string; root_path: string; trusted: boolean }[];
  grants: { id: string; workspace_id: string; kind: "path" | "domain" | "app"; value: string }[];
}
export interface SkillDef {
  id: string; name: string; description: string; workflow: string[]; inputs: string[]; enabled: boolean;
}
export interface SettingsResponse {
  version: string; planner: string; approval_ttl_seconds: number;
  max_retries_per_step: number; max_retries_per_task: number; trusted_workspaces: string[];
}
```
add to `api`:
```ts
  permissions: () => request<PermissionsResponse>("/api/permissions"),
  revokeGrant: (id: string) => request<{ revoked: string }>(`/api/permissions/grants/${id}`, { method: "DELETE" }),
  skills: () => request<SkillDef[]>("/api/skills"),
  setSkillEnabled: (id: string, enabled: boolean) =>
    request<SkillDef>(`/api/skills/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  settings: () => request<SettingsResponse>("/api/settings"),
```

- [ ] **Step 2: typecheck** `pnpm -C apps/desktop typecheck` → clean. **Commit** `feat(desktop): api client methods for permissions/skills/settings`

---

### Task 4: wire the three views + tests

**Files:** Modify `views/{Permissions,Skills,Settings}.tsx`, `views/views.test.tsx`.

- [ ] **Step 1: Rewrite `Permissions.tsx`** — `useQuery(["permissions"], api.permissions)`; render workspace roots + grants grouped by kind; Revoke button → `useMutation(api.revokeGrant)` → `invalidateQueries(["permissions"])`. Loading + error text. Replace the amber "mock data" badge with a neutral "live" badge (or none).

- [ ] **Step 2: Rewrite `Skills.tsx`** — `useQuery(["skills"], api.skills)`; map real skills; `Switch` `checked={s.enabled}` `onCheckedChange` → `useMutation((v)=>api.setSkillEnabled(s.id, v))` → invalidate. Empty state paragraph (spec §4). Remove badge.

- [ ] **Step 3: Rewrite `Settings.tsx`** — `useQuery(["settings"], api.settings)`; show planner, approval TTL, retry budgets, trusted workspaces, daemon version in the existing read-only card layout. Remove the retention card (not real) + voice card stays as a disabled Phase-3 placeholder (clearly future, not "mock data"). Remove badge.

- [ ] **Step 4: Update `views.test.tsx`** — wrap renders in a `QueryClientProvider`; stub `fetch` (and `VITE_THOTH_TOKEN`) to return each endpoint's JSON; assert real values render; Permissions revoke fires DELETE; Skills toggle fires PATCH; Skills empty state shows when `[]`. Concrete pattern:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
// helper: renderWithQuery(ui) wraps in a fresh QueryClient (retry:false)
// beforeEach: vi.stubEnv("VITE_THOTH_TOKEN","t"); vi.stubGlobal("fetch", routeMock)
// routeMock returns permissions/skills/settings JSON by URL; asserts via findByText
```

- [ ] **Step 5:** `pnpm -C apps/desktop test -- --run && pnpm -C apps/desktop typecheck && pnpm -C apps/desktop lint && pnpm -C apps/desktop build` → all green. **Commit** `feat(desktop): wire Permissions/Skills/Settings to real daemon state`

---

### Task 5: docs, full gate, live verification

- [ ] **Step 1: ADR-016** (spec §6) → `docs/DECISIONS.md`.
- [ ] **Step 2: STATUS + MILESTONES** — Permissions/Skills/Settings now live (mock badges gone); note skills list is empty until the engine ships; settings read-only; check the two MILESTONES lines (Permissions view wired; Skills view — partial: listing/toggle, engine later). Bump daemon test count. Keep no-autonomous-control statement.
- [ ] **Step 3: Daemon gate** — pytest (hang-guard), ruff, format, mypy.
- [ ] **Step 4: Desktop gate** — test, lint, typecheck, build.
- [ ] **Step 5: Live verify** — daemon up (`THOTH_SESSION_TOKEN=x`): curl `/api/skills` (`[]`), `/api/settings` (real) with token → 200, without → 401.
- [ ] **Step 6: Commit** `docs: ADR-016 + status for views wiring (slice 9)`

---

## Self-Review
**Spec coverage:** §3 daemon APIs → T1/T2; §4 client+views → T3/T4; §5 tests → T1/T2/T4/T5; §6 ADR → T5. **Placeholders:** none; ADR-016 next; view-test helper sketched then concretized in T4. **Type consistency:** `SkillStore.set_enabled -> SkillDefinition | None`, `api.skills()->SkillDef[]`, `setSkillEnabled(id,enabled)`, settings keys identical across daemon (T2) + client (T3) + test (T2/T4).
