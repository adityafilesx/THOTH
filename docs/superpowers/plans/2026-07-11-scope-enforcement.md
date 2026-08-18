# Scope Enforcement + Permission Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the unenforced-`resource_scope` gap with a central `ScopeEnforcer` (orchestrator pre-EXECUTING gate + registry backstop) backed by a persistent, user-driven permission store and API — the safety backbone every real Phase 3 adapter stands on.

**Architecture:** Pure path primitives (`security/paths.py`) feed a stateless `ScopeEnforcer` (`core/scope.py`). Tools declare `requested_scope(args)`; the orchestrator checks it against a freshly-resolved effective scope before entering `EXECUTING`, and `registry.execute` re-checks as a backstop. Grants live in SQLite (`PermissionStore`) behind a typed `/api/permissions` router; only trusted user action mutates them. **No real file/shell/app I/O ships in this slice.**

**Tech Stack:** Python 3.12 (uv), FastAPI, Pydantic v2, SQLAlchemy 2 async + aiosqlite, Alembic, pytest + pytest-asyncio + httpx.

## Global Constraints

- Python 3.12 via uv. Run daemon tests with `uv run --project apps/daemon pytest apps/daemon/tests`.
- `mypy apps/daemon/src` runs **strict** and must stay clean; `ruff check` + `ruff format --check` clean.
- Every Pydantic boundary model uses `extra="forbid"` (`StrictModel` or `ConfigDict(extra="forbid")`).
- Safety invariants unchanged: no execution outside `EXECUTING`; effective risk never downgrades; audit store append-only (no update/delete surface added); redaction runs at every serialization boundary.
- **The existing 256 daemon + 42 desktop tests must stay green.** Mocks override nothing, so they request an empty scope and are always allowed. All new constructor/function params default so existing call sites compile unchanged.
- Work on branch `phase-3/scope-enforcement`. Every commit message ends with the trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (shown via a second `-m`). Do **not** push.
- This slice adds **no** real I/O and makes **no** capability claim. `docs/STATUS.md` must continue to state OmniMac cannot control the computer.

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `apps/daemon/src/omnimac_daemon/security/paths.py` | Create | `expand_and_resolve`, `is_within`, `is_denied_path` + denylists. |
| `apps/daemon/src/omnimac_daemon/core/scope.py` | Create | `ScopeViolation`, stateless `ScopeEnforcer.check`. |
| `apps/daemon/src/omnimac_daemon/schemas/contracts.py` | Modify | Add `PermissionKind`, `PermissionGrant`. |
| `apps/daemon/src/omnimac_daemon/schemas/__init__.py` | Modify | Export the two new names. |
| `apps/daemon/src/omnimac_daemon/storage/models.py` | Modify | Add `WorkspaceRow`, `PermissionGrantRow`. |
| `apps/daemon/alembic/versions/0002_permissions_and_workspaces.py` | Create | Migration for the two tables. |
| `apps/daemon/src/omnimac_daemon/storage/permissions.py` | Create | `PermissionStore` + `effective_scope`. |
| `apps/daemon/src/omnimac_daemon/tools/base.py` | Modify | Add `requested_scope(args) -> ResourceScope` (default empty). |
| `apps/daemon/src/omnimac_daemon/tools/registry.py` | Modify | Backstop scope check in `execute(invocation, allowed_scope=None)`. |
| `apps/daemon/src/omnimac_daemon/core/orchestrator.py` | Modify | Primary pre-EXECUTING gate; thread `enforcer` + `scope_provider`. |
| `apps/daemon/src/omnimac_daemon/api/permissions.py` | Create | REST router. |
| `apps/daemon/src/omnimac_daemon/app.py` | Modify | Build store, seed default workspace, wire enforcer + provider + router. |
| `apps/daemon/src/omnimac_daemon/schemas/export.py` | Modify | Add `PermissionGrant` to exported contracts. |
| `docs/DECISIONS.md`, `docs/STATUS.md`, `docs/MILESTONES.md` | Modify | ADR + truthful status. |

Tests: `tests/security/test_paths.py`, `tests/core/test_scope.py`, `tests/schemas/test_permission_schema.py`, `tests/storage/test_permissions_store.py`, `tests/tools/test_registry.py` (extend), `tests/core/test_scope_integration.py`, `tests/api/test_permissions_api.py`.

---

### Task 1: Path safety primitives

**Files:**
- Create: `apps/daemon/src/omnimac_daemon/security/paths.py`
- Test: `apps/daemon/tests/security/test_paths.py`

**Interfaces:**
- Produces: `expand_and_resolve(path: str | Path) -> Path`, `is_within(path: str | Path, root: str | Path) -> bool`, `is_denied_path(path: str | Path) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/security/test_paths.py
from pathlib import Path

from omnimac_daemon.security.paths import expand_and_resolve, is_denied_path, is_within


def test_expand_user_home() -> None:
    assert expand_and_resolve("~/projects/omnimac") == (Path.home() / "projects" / "omnimac").resolve()


def test_is_within_child_and_self() -> None:
    root = Path.home() / "projects" / "omnimac"
    assert is_within(root / "src" / "main.py", root)
    assert is_within(root, root)


def test_is_within_rejects_parent_and_sibling() -> None:
    root = Path.home() / "projects" / "omnimac"
    assert not is_within(Path.home() / "projects", root)
    assert not is_within(Path.home() / "projects" / "other", root)


def test_is_within_rejects_dotdot_escape() -> None:
    root = Path.home() / "projects" / "omnimac"
    assert not is_within(root / ".." / "secret.txt", root)


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x")
    link = root / "link.txt"
    link.symlink_to(outside / "secret.txt")
    assert not is_within(link, root)  # lives in root, resolves outside


def test_denylist_credential_dirs() -> None:
    assert is_denied_path(Path.home() / ".ssh" / "id_rsa")
    assert is_denied_path(Path.home() / ".aws" / "credentials")
    assert is_denied_path(Path.home() / ".config" / "gcloud" / "creds.db")
    assert is_denied_path(Path.home() / "Library" / "Keychains" / "login.keychain-db")


def test_denylist_name_globs() -> None:
    assert is_denied_path(Path.home() / "projects" / "omnimac" / ".env")
    assert is_denied_path(Path.home() / "projects" / "omnimac" / ".env.local")
    assert is_denied_path(Path.home() / "certs" / "server.pem")
    assert is_denied_path(Path.home() / ".netrc")


def test_normal_project_path_not_denied() -> None:
    assert not is_denied_path(Path.home() / "projects" / "omnimac" / "README.md")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/security/test_paths.py -q`
Expected: FAIL — `ModuleNotFoundError: omnimac_daemon.security.paths`.

- [ ] **Step 3: Write minimal implementation**

```python
# apps/daemon/src/omnimac_daemon/security/paths.py
"""Path safety primitives for scoped filesystem and shell access.

Pure functions over paths: user-directory expansion, symlink-safe
resolution, containment checks, and an always-denied set of credential and
system locations (docs/TOOL_CONTRACTS.md §4, threat T5). No file contents
are read or written here."""

from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path

# Denied even when nested inside an approved root. Anchored at the user home.
_DENY_DIR_PARTS: tuple[tuple[str, ...], ...] = (
    (".ssh",),
    (".aws",),
    (".config", "gcloud"),
    ("Library", "Keychains"),
    ("Library", "Keychain"),
)

# Denied by basename anywhere.
DENY_NAME_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*.pem",
    ".netrc",
)


def expand_and_resolve(path: str | Path) -> Path:
    """Expand ``~`` and ``$VARS``, then resolve to an absolute, symlink-free
    path. ``strict=False`` so a not-yet-created target resolves as far as it
    exists and the remainder is normalized lexically."""
    expanded = os.path.expanduser(os.path.expandvars(str(path)))
    return Path(expanded).resolve()


def is_within(path: str | Path, root: str | Path) -> bool:
    """True iff *path* equals *root* or is a descendant, after resolving both.
    A symlink that escapes *root* resolves outside it and returns False."""
    rp = expand_and_resolve(path)
    rr = expand_and_resolve(root)
    return rp == rr or rr in rp.parents


def is_denied_path(path: str | Path) -> bool:
    """True if *path* resolves into a credential/system location that is denied
    regardless of any grant."""
    rp = expand_and_resolve(path)
    home = Path.home().resolve()
    for parts in _DENY_DIR_PARTS:
        deny_root = home.joinpath(*parts)
        if rp == deny_root or deny_root in rp.parents:
            return True
    return any(fnmatch(rp.name, glob) for glob in DENY_NAME_GLOBS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/security/test_paths.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/security/paths.py apps/daemon/tests/security/test_paths.py
git commit -m "feat(security): path safety primitives (expand/resolve, containment, denylist)" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: ScopeEnforcer

**Files:**
- Create: `apps/daemon/src/omnimac_daemon/core/scope.py`
- Test: `apps/daemon/tests/core/test_scope.py`

**Interfaces:**
- Consumes: `is_within`, `is_denied_path` (Task 1); `ResourceScope` (schemas).
- Produces: `ScopeViolation(kind: str, value: str, reason: str)` (Exception with `.kind/.value/.reason`); `ScopeEnforcer().check(requested: ResourceScope, allowed: ResourceScope) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/core/test_scope.py
from pathlib import Path

import pytest

from omnimac_daemon.core.scope import ScopeEnforcer, ScopeViolation
from omnimac_daemon.schemas import ResourceScope


@pytest.fixture()
def enforcer() -> ScopeEnforcer:
    return ScopeEnforcer()


def _allowed(root: str) -> ResourceScope:
    return ResourceScope(paths=[root], domains=["example.com"], apps=["Safari"])


def test_in_scope_path_allowed(enforcer: ScopeEnforcer) -> None:
    root = str(Path.home() / "projects" / "omnimac")
    enforcer.check(ResourceScope(paths=[root + "/README.md"]), _allowed(root))


def test_out_of_scope_path_denied(enforcer: ScopeEnforcer) -> None:
    root = str(Path.home() / "projects" / "omnimac")
    with pytest.raises(ScopeViolation) as exc:
        enforcer.check(ResourceScope(paths=[str(Path.home() / "other" / "x.txt")]), _allowed(root))
    assert exc.value.kind == "path"


def test_denied_path_inside_root_denied(enforcer: ScopeEnforcer) -> None:
    with pytest.raises(ScopeViolation) as exc:
        enforcer.check(
            ResourceScope(paths=[str(Path.home() / ".ssh" / "id_rsa")]),
            ResourceScope(paths=[str(Path.home())]),
        )
    assert "denied" in exc.value.reason


def test_domain_allowed_and_denied(enforcer: ScopeEnforcer) -> None:
    root = str(Path.home())
    enforcer.check(ResourceScope(domains=["EXAMPLE.com"]), _allowed(root))  # case-insensitive
    with pytest.raises(ScopeViolation):
        enforcer.check(ResourceScope(domains=["evil.com"]), _allowed(root))


def test_app_allowed_and_denied(enforcer: ScopeEnforcer) -> None:
    root = str(Path.home())
    enforcer.check(ResourceScope(apps=["Safari"]), _allowed(root))
    with pytest.raises(ScopeViolation):
        enforcer.check(ResourceScope(apps=["Terminal"]), _allowed(root))


def test_empty_requested_scope_always_allowed(enforcer: ScopeEnforcer) -> None:
    enforcer.check(ResourceScope(), ResourceScope())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/core/test_scope.py -q`
Expected: FAIL — `ModuleNotFoundError: omnimac_daemon.core.scope`.

- [ ] **Step 3: Write minimal implementation**

```python
# apps/daemon/src/omnimac_daemon/core/scope.py
"""Scope enforcement.

A stateless decision: does an invocation's requested scope fall inside the
effective allowed scope? Paths must resolve inside an approved root and
outside the denylist; domains and apps must be explicitly granted. All inputs
are typed ResourceScope values from trusted sources (plan args + permission
store) — no free text reaches this decision (threats T1/T3)."""

from __future__ import annotations

from omnimac_daemon.schemas import ResourceScope
from omnimac_daemon.security.paths import is_denied_path, is_within


class ScopeViolation(Exception):
    def __init__(self, kind: str, value: str, reason: str) -> None:
        self.kind = kind
        self.value = value
        self.reason = reason
        super().__init__(f"scope violation ({kind}={value!r}): {reason}")


class ScopeEnforcer:
    """Pure: no state, no I/O. Raises ScopeViolation on the first offending
    target, otherwise returns None."""

    def check(self, requested: ResourceScope, allowed: ResourceScope) -> None:
        for path in requested.paths:
            self._check_path(path, allowed.paths)
        allowed_domains = {d.lower() for d in allowed.domains}
        for domain in requested.domains:
            if domain.lower() not in allowed_domains:
                raise ScopeViolation("domain", domain, "not in approved domains")
        allowed_apps = set(allowed.apps)
        for app in requested.apps:
            if app not in allowed_apps:
                raise ScopeViolation("app", app, "not in approved apps")

    @staticmethod
    def _check_path(path: str, roots: list[str]) -> None:
        if is_denied_path(path):
            raise ScopeViolation("path", path, "denied credential/system location")
        if not any(is_within(path, root) for root in roots):
            raise ScopeViolation("path", path, "outside all approved roots")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/core/test_scope.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/core/scope.py apps/daemon/tests/core/test_scope.py
git commit -m "feat(core): stateless ScopeEnforcer over path/domain/app targets" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: PermissionGrant contract + tables + migration

**Files:**
- Modify: `apps/daemon/src/omnimac_daemon/schemas/contracts.py`
- Modify: `apps/daemon/src/omnimac_daemon/schemas/__init__.py`
- Modify: `apps/daemon/src/omnimac_daemon/storage/models.py`
- Create: `apps/daemon/alembic/versions/0002_permissions_and_workspaces.py`
- Test: `apps/daemon/tests/schemas/test_permission_schema.py`

**Interfaces:**
- Produces: `PermissionKind = Literal["path","domain","app"]`; `PermissionGrant{id, workspace_id, kind, value, granted_at, revoked}`; SQLAlchemy rows `WorkspaceRow`, `PermissionGrantRow`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/schemas/test_permission_schema.py
import pytest
from pydantic import ValidationError

from omnimac_daemon.schemas import PermissionGrant
from omnimac_daemon.storage.models import Base


def test_permission_grant_defaults() -> None:
    g = PermissionGrant(workspace_id="w1", kind="path", value="~/projects/omnimac")
    assert g.revoked is False and g.id


def test_permission_grant_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        PermissionGrant(workspace_id="w1", kind="network", value="x")


def test_permission_grant_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        PermissionGrant(workspace_id="w1", kind="path", value="x", foo=1)


def test_new_tables_registered() -> None:
    assert "workspace_profiles" in Base.metadata.tables
    assert "permission_grants" in Base.metadata.tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/schemas/test_permission_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'PermissionGrant'`.

- [ ] **Step 3a: Add the contract**

In `apps/daemon/src/omnimac_daemon/schemas/contracts.py`, after the `WorkspaceProfile` class, append:

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

- [ ] **Step 3b: Export it**

In `apps/daemon/src/omnimac_daemon/schemas/__init__.py`, add `PermissionGrant` and `PermissionKind` to the `from omnimac_daemon.schemas.contracts import (...)` block and to `__all__` (keep alphabetical grouping):

```python
    PermissionGrant,
    PermissionKind,
```
(both in the import list and, as `"PermissionGrant",` / `"PermissionKind",`, in `__all__`).

- [ ] **Step 3c: Add the tables**

In `apps/daemon/src/omnimac_daemon/storage/models.py`, append (imports already cover `String, Text, Boolean, DateTime, JSON, Mapped, mapped_column`):

```python
class WorkspaceRow(Base):
    __tablename__ = "workspace_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    root_path: Mapped[str] = mapped_column(Text)
    trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_domains_json: Mapped[list] = mapped_column(JSON, default=list)  # type: ignore[type-arg]
    approved_apps_json: Mapped[list] = mapped_column(JSON, default=list)  # type: ignore[type-arg]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PermissionGrantRow(Base):
    __tablename__ = "permission_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(Text)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

- [ ] **Step 3d: Write the migration**

```python
# apps/daemon/alembic/versions/0002_permissions_and_workspaces.py
"""permissions and workspaces

Revision ID: 0002_permissions
Revises: 481eb5e99a59
Create Date: 2026-07-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_permissions"
down_revision: str | None = "481eb5e99a59"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("trusted", sa.Boolean(), nullable=False),
        sa.Column("approved_domains_json", sa.JSON(), nullable=False),
        sa.Column("approved_apps_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "permission_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_permission_grants_workspace_id"),
        "permission_grants",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_permission_grants_workspace_id"), table_name="permission_grants")
    op.drop_table("permission_grants")
    op.drop_table("workspace_profiles")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/schemas/test_permission_schema.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/schemas/contracts.py apps/daemon/src/omnimac_daemon/schemas/__init__.py \
        apps/daemon/src/omnimac_daemon/storage/models.py \
        apps/daemon/alembic/versions/0002_permissions_and_workspaces.py \
        apps/daemon/tests/schemas/test_permission_schema.py
git commit -m "feat(storage): PermissionGrant contract, workspace/grant tables, migration 0002" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: PermissionStore

**Files:**
- Create: `apps/daemon/src/omnimac_daemon/storage/permissions.py`
- Test: `apps/daemon/tests/storage/test_permissions_store.py`

**Interfaces:**
- Consumes: `WorkspaceRow`, `PermissionGrantRow` (Task 3); `WorkspaceProfile`, `PermissionGrant`, `ResourceScope` (schemas); `init_schema/make_engine/make_session_factory` (storage.db).
- Produces: `PermissionStore(session_factory)` with `upsert_workspace`, `list_workspaces`, `get_workspace`, `add_grant`, `revoke_grant(grant_id) -> bool`, `list_grants(include_revoked=False)`, `effective_scope(workspace_id) -> ResourceScope`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/storage/test_permissions_store.py
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from omnimac_daemon.schemas import PermissionGrant, WorkspaceProfile
from omnimac_daemon.storage.db import init_schema, make_engine, make_session_factory
from omnimac_daemon.storage.permissions import PermissionStore


@pytest.fixture()
async def store(tmp_path: Path) -> AsyncIterator[PermissionStore]:
    engine = make_engine(tmp_path / "perm.db")
    await init_schema(engine)
    yield PermissionStore(make_session_factory(engine))


async def test_upsert_and_list_workspace(store: PermissionStore) -> None:
    await store.upsert_workspace(WorkspaceProfile(name="default", root_path="~/projects/omnimac", trusted=True))
    listed = await store.list_workspaces()
    assert len(listed) == 1 and listed[0].root_path == "~/projects/omnimac"


async def test_add_list_revoke_grant(store: PermissionStore) -> None:
    g = PermissionGrant(workspace_id="w1", kind="domain", value="example.com")
    await store.add_grant(g)
    assert [x.value for x in await store.list_grants()] == ["example.com"]
    assert await store.revoke_grant(g.id) is True
    assert await store.list_grants() == []
    assert await store.revoke_grant("missing") is False


async def test_effective_scope_unions_workspace_and_grants(store: PermissionStore) -> None:
    await store.upsert_workspace(
        WorkspaceProfile(
            id="w1", name="default", root_path="~/projects/omnimac", trusted=True,
            approved_domains=["docs.python.org"], approved_apps=["Safari"],
        )
    )
    await store.add_grant(PermissionGrant(workspace_id="w1", kind="path", value="~/scratch"))
    await store.add_grant(PermissionGrant(workspace_id="w1", kind="domain", value="example.com"))
    revoked = PermissionGrant(workspace_id="w1", kind="app", value="Terminal")
    await store.add_grant(revoked)
    await store.revoke_grant(revoked.id)

    scope = await store.effective_scope("w1")
    assert set(scope.paths) == {"~/projects/omnimac", "~/scratch"}
    assert set(scope.domains) == {"docs.python.org", "example.com"}
    assert scope.apps == ["Safari"]  # revoked Terminal excluded


async def test_grants_persist_across_store_instances(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "persist.db")
    await init_schema(engine)
    sf = make_session_factory(engine)
    await PermissionStore(sf).add_grant(PermissionGrant(workspace_id="w1", kind="path", value="~/x"))
    reopened = await PermissionStore(sf).list_grants()
    assert [g.value for g in reopened] == ["~/x"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/storage/test_permissions_store.py -q`
Expected: FAIL — `ModuleNotFoundError: omnimac_daemon.storage.permissions`.

- [ ] **Step 3: Write minimal implementation**

```python
# apps/daemon/src/omnimac_daemon/storage/permissions.py
"""Permission store — persistent workspaces and scope grants.

Mirrors AuditStore's async-session style. Resolves the effective allowed
ResourceScope (workspace roots/domains/apps + active grants) the scope
enforcer checks against. Only trusted, user-initiated API calls mutate it;
untrusted content has no path here (threats T1/T3)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from omnimac_daemon.schemas import PermissionGrant, ResourceScope, WorkspaceProfile
from omnimac_daemon.storage.models import PermissionGrantRow, WorkspaceRow


class PermissionStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def upsert_workspace(self, profile: WorkspaceProfile) -> WorkspaceProfile:
        async with self._session_factory() as session:
            row = await session.get(WorkspaceRow, profile.id)
            if row is None:
                row = WorkspaceRow(id=profile.id)
                session.add(row)
            row.name = profile.name
            row.root_path = profile.root_path
            row.trusted = profile.trusted
            row.approved_domains_json = list(profile.approved_domains)
            row.approved_apps_json = list(profile.approved_apps)
            await session.commit()
            return profile

    async def list_workspaces(self) -> list[WorkspaceProfile]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(WorkspaceRow))).scalars().all()
            return [self._to_profile(r) for r in rows]

    async def get_workspace(self, workspace_id: str) -> WorkspaceProfile | None:
        async with self._session_factory() as session:
            row = await session.get(WorkspaceRow, workspace_id)
            return self._to_profile(row) if row else None

    async def add_grant(self, grant: PermissionGrant) -> PermissionGrant:
        async with self._session_factory() as session:
            session.add(
                PermissionGrantRow(
                    id=grant.id,
                    workspace_id=grant.workspace_id,
                    kind=grant.kind,
                    value=grant.value,
                    revoked=grant.revoked,
                    granted_at=grant.granted_at,
                )
            )
            await session.commit()
            return grant

    async def revoke_grant(self, grant_id: str) -> bool:
        async with self._session_factory() as session:
            row = await session.get(PermissionGrantRow, grant_id)
            if row is None:
                return False
            row.revoked = True
            await session.commit()
            return True

    async def list_grants(self, include_revoked: bool = False) -> list[PermissionGrant]:
        async with self._session_factory() as session:
            stmt = select(PermissionGrantRow)
            if not include_revoked:
                stmt = stmt.where(PermissionGrantRow.revoked.is_(False))
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_grant(r) for r in rows]

    async def effective_scope(self, workspace_id: str) -> ResourceScope:
        profile = await self.get_workspace(workspace_id)
        paths: list[str] = []
        domains: list[str] = []
        apps: list[str] = []
        if profile is not None:
            if profile.root_path:
                paths.append(profile.root_path)
            domains.extend(profile.approved_domains)
            apps.extend(profile.approved_apps)
        for grant in await self.list_grants():
            if grant.workspace_id != workspace_id:
                continue
            if grant.kind == "path":
                paths.append(grant.value)
            elif grant.kind == "domain":
                domains.append(grant.value)
            elif grant.kind == "app":
                apps.append(grant.value)
        return ResourceScope(paths=paths, domains=domains, apps=apps)

    @staticmethod
    def _to_profile(row: WorkspaceRow) -> WorkspaceProfile:
        return WorkspaceProfile(
            id=row.id,
            name=row.name,
            root_path=row.root_path,
            trusted=row.trusted,
            approved_domains=list(row.approved_domains_json or []),
            approved_apps=list(row.approved_apps_json or []),
        )

    @staticmethod
    def _to_grant(row: PermissionGrantRow) -> PermissionGrant:
        return PermissionGrant(
            id=row.id,
            workspace_id=row.workspace_id,
            kind=row.kind,  # type: ignore[arg-type]
            value=row.value,
            granted_at=row.granted_at,
            revoked=row.revoked,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/storage/test_permissions_store.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/storage/permissions.py apps/daemon/tests/storage/test_permissions_store.py
git commit -m "feat(storage): PermissionStore with effective_scope resolution" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Tool `requested_scope` hook + registry backstop

**Files:**
- Modify: `apps/daemon/src/omnimac_daemon/tools/base.py`
- Modify: `apps/daemon/src/omnimac_daemon/tools/registry.py`
- Test: `apps/daemon/tests/tools/test_registry.py` (extend)

**Interfaces:**
- Consumes: `ScopeEnforcer`, `ScopeViolation` (Task 2); `ResourceScope` (schemas).
- Produces: `ToolDefinition.requested_scope(self, args) -> ResourceScope` (default empty); `ToolRegistry.execute(invocation, allowed_scope: ResourceScope | None = None) -> ToolResult`.

- [ ] **Step 1: Write the failing test** (append to `apps/daemon/tests/tools/test_registry.py`)

Add these imports at the top of the file:

```python
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from omnimac_daemon.schemas import ResourceScope
```

Append at the end:

```python
class _ScopedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str


class _ScopedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


class _ScopedTool(ToolDefinition[_ScopedIn, _ScopedOut]):
    name = "scoped_probe"
    description = "test tool that declares it touches a path"
    input_model = _ScopedIn
    output_model = _ScopedOut
    default_risk = RiskLevel.R1

    def requested_scope(self, args: _ScopedIn) -> ResourceScope:  # type: ignore[override]
        return ResourceScope(paths=[args.path])

    async def run(self, args: _ScopedIn, dry_run: bool) -> _ScopedOut:
        return _ScopedOut(ok=True)


class TestScopeBackstop:
    async def test_in_scope_allowed(self) -> None:
        registry = ToolRegistry()
        registry.register(_ScopedTool())
        allowed = ResourceScope(paths=[str(Path.home() / "projects")])
        inv = invocation("scoped_probe", {"path": str(Path.home() / "projects" / "a.txt")})
        assert (await registry.execute(inv, allowed)).ok

    async def test_out_of_scope_refused(self) -> None:
        registry = ToolRegistry()
        registry.register(_ScopedTool())
        allowed = ResourceScope(paths=[str(Path.home() / "projects")])
        inv = invocation("scoped_probe", {"path": str(Path.home() / "secret" / "a.txt")})
        result = await registry.execute(inv, allowed)
        assert not result.ok and "scope violation" in (result.error or "")

    async def test_mock_tools_unaffected_without_scope(self) -> None:
        registry = build_registry()
        assert (await registry.execute(invocation("mock_read_file", {"path": "/anything"}))).ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/tools/test_registry.py::TestScopeBackstop -q`
Expected: FAIL — `execute()` takes no `allowed_scope` argument (TypeError).

- [ ] **Step 3a: Add the base hook**

In `apps/daemon/src/omnimac_daemon/tools/base.py`, add this method to `ToolDefinition` (after `parse_arguments`; `ResourceScope` is already imported):

```python
    def requested_scope(self, args: Any) -> ResourceScope:
        """The concrete paths/domains/apps this invocation will touch. The
        orchestrator and executor check these against the effective allowed
        scope. Default: touches nothing (mocks and pure-compute tools)."""
        return ResourceScope()
```

- [ ] **Step 3b: Add the registry backstop**

In `apps/daemon/src/omnimac_daemon/tools/registry.py`, add imports:

```python
from omnimac_daemon.core.scope import ScopeEnforcer, ScopeViolation
from omnimac_daemon.schemas import ResourceScope, RiskLevel, ToolInvocation, ToolResult
```

Add an enforcer in `__init__`:

```python
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition[Any, Any]] = {}
        self._enforcer = ScopeEnforcer()
```

Change the `execute` signature and insert the check after argument parsing, before timing:

```python
    async def execute(
        self, invocation: ToolInvocation, allowed_scope: ResourceScope | None = None
    ) -> ToolResult:
        tool = self.get(invocation.tool_name)  # raises UnknownToolError
        args = tool.parse_arguments(invocation)  # raises ValidationError

        try:
            self._enforcer.check(tool.requested_scope(args), allowed_scope or ResourceScope())
        except ScopeViolation as exc:
            return ToolResult(invocation_id=invocation.id, ok=False, error=f"scope violation: {exc}")

        started = time.perf_counter()
        ...  # unchanged from here
```

Note: `core.scope` imports only `schemas` and `security.paths`, so `tools.registry → core.scope` introduces no import cycle.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/tools/test_registry.py -q`
Expected: PASS (all prior tests + 3 new). The mock-tool tests are unaffected (empty requested scope).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/tools/base.py apps/daemon/src/omnimac_daemon/tools/registry.py \
        apps/daemon/tests/tools/test_registry.py
git commit -m "feat(tools): requested_scope hook + registry scope backstop" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Orchestrator primary scope gate

**Files:**
- Modify: `apps/daemon/src/omnimac_daemon/core/orchestrator.py`
- Test: `apps/daemon/tests/core/test_scope_integration.py`

**Interfaces:**
- Consumes: `ScopeEnforcer`, `ScopeViolation` (Task 2); `requested_scope` (Task 5); `PlannerAdapter`, `ExecutionPlan`, `PlanStep`, `ResourceScope`.
- Produces: `guarded_execute(machine, registry, invocation, allowed_scope=None)`; `Orchestrator(..., enforcer=None, scope_provider=None)` where `scope_provider: Callable[[], Awaitable[ResourceScope]]`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/core/test_scope_integration.py
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from omnimac_daemon.audit.store import AuditStore
from omnimac_daemon.core.approvals import ApprovalEngine
from omnimac_daemon.core.orchestrator import Orchestrator
from omnimac_daemon.core.planner import PlannerAdapter
from omnimac_daemon.core.policy import PolicyEngine
from omnimac_daemon.core.recovery import RecoveryController
from omnimac_daemon.core.scope import ScopeEnforcer
from omnimac_daemon.core.verification import VerificationEngine
from omnimac_daemon.schemas import (
    ExecutionPlan,
    PlanStep,
    ResourceScope,
    RiskLevel,
    TaskState,
    VerificationStrategy,
    WorkspaceProfile,
)
from omnimac_daemon.storage.db import init_schema, make_engine, make_session_factory
from omnimac_daemon.tools.base import ToolDefinition
from omnimac_daemon.tools.registry import ToolRegistry


class _ProbeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str


class _ProbeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


class _ProbeTool(ToolDefinition[_ProbeIn, _ProbeOut]):
    name = "scoped_probe"
    description = "reads a path"
    input_model = _ProbeIn
    output_model = _ProbeOut
    default_risk = RiskLevel.R0
    verification = VerificationStrategy.NONE_READONLY

    def __init__(self) -> None:
        super().__init__()
        self.ran = 0

    def requested_scope(self, args: _ProbeIn) -> ResourceScope:  # type: ignore[override]
        return ResourceScope(paths=[args.path])

    async def run(self, args: _ProbeIn, dry_run: bool) -> _ProbeOut:
        self.ran += 1
        return _ProbeOut(ok=True)


class _OneStepPlanner(PlannerAdapter):
    def __init__(self, path: str) -> None:
        self._path = path

    def plan(self, task_id: str, goal: str) -> ExecutionPlan:
        return ExecutionPlan(
            task_id=task_id,
            summary=goal,
            steps=[PlanStep(index=0, title="probe", tool_name="scoped_probe",
                            arguments={"path": self._path}, declared_risk=RiskLevel.R0)],
        )


async def _build(tmp_path: Path, allowed_paths: list[str], requested_path: str):
    engine = make_engine(tmp_path / "s.db")
    await init_schema(engine)

    async def publish(event_type: str, payload: dict) -> None:
        return None

    async def provider() -> ResourceScope:
        return ResourceScope(paths=allowed_paths)

    registry = ToolRegistry()
    tool = _ProbeTool()
    registry.register(tool)
    orch = Orchestrator(
        registry=registry,
        policy=PolicyEngine(),
        approvals=ApprovalEngine(ttl_seconds=60),
        verifier=VerificationEngine(),
        recovery=RecoveryController(),
        audit=AuditStore(make_session_factory(engine)),
        planner=_OneStepPlanner(requested_path),
        publish=publish,
        workspace=WorkspaceProfile(name="w", root_path=allowed_paths[0], trusted=True),
        enforcer=ScopeEnforcer(),
        scope_provider=provider,
    )
    return orch, tool


async def test_in_scope_step_completes(tmp_path: Path) -> None:
    root = str(Path.home() / "projects" / "omnimac")
    orch, tool = await _build(tmp_path, [root], root + "/a.txt")
    task = await orch.submit("probe")
    settled = await orch.settle(task.id)
    assert settled.state is TaskState.COMPLETED and tool.ran == 1


async def test_out_of_scope_step_fails_before_executing(tmp_path: Path) -> None:
    root = str(Path.home() / "projects" / "omnimac")
    orch, tool = await _build(tmp_path, [root], str(Path.home() / "secret" / "a.txt"))
    task = await orch.submit("probe")
    settled = await orch.settle(task.id)
    assert settled.state is TaskState.FAILED
    assert tool.ran == 0
    audit = await orch.task_audit(task.id)
    types = [e.event_type for e in audit]
    assert "scope.denied" in types
    assert not any(e.event_type == "state.transition" and e.payload.get("to") == "EXECUTING" for e in audit)
    assert not any(e.event_type == "tool.result" for e in audit)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/core/test_scope_integration.py -q`
Expected: FAIL — `Orchestrator.__init__() got an unexpected keyword argument 'enforcer'`.

- [ ] **Step 3a: Thread scope through `guarded_execute`**

In `apps/daemon/src/omnimac_daemon/core/orchestrator.py`, add imports:

```python
from pydantic import ValidationError

from omnimac_daemon.core.scope import ScopeEnforcer, ScopeViolation
```
and add `ResourceScope` to the existing `from omnimac_daemon.schemas import (...)` block.

Add a module-level default provider (after the `Publish` type alias):

```python
async def _empty_scope() -> ResourceScope:
    return ResourceScope()
```

Change `guarded_execute`:

```python
async def guarded_execute(
    machine: TaskStateMachine,
    registry: ToolRegistry,
    invocation: ToolInvocation,
    allowed_scope: ResourceScope | None = None,
) -> ToolResult:
    """The ONLY path to a tool. Refuses unless the task is EXECUTING."""
    if machine.state is not TaskState.EXECUTING:
        raise ExecutionStateError(
            f"tool execution requires EXECUTING state, not {machine.state.value}"
        )
    return await registry.execute(invocation, allowed_scope)
```

- [ ] **Step 3b: Accept enforcer + provider on the runner and orchestrator**

In `_TaskRunner.__init__`, add two keyword params and store them:

```python
        workspace: WorkspaceProfile,
        enforcer: ScopeEnforcer,
        scope_provider: Callable[[], Awaitable[ResourceScope]],
    ) -> None:
        ...
        self._workspace = workspace
        self._enforcer = enforcer
        self._scope_provider = scope_provider
```

In `Orchestrator.__init__`, add optional params (defaults keep existing callers working):

```python
        workspace: WorkspaceProfile,
        enforcer: ScopeEnforcer | None = None,
        scope_provider: Callable[[], Awaitable[ResourceScope]] | None = None,
    ) -> None:
        ...
        self._workspace = workspace
        self._enforcer = enforcer or ScopeEnforcer()
        self._scope_provider = scope_provider or _empty_scope
```

In `Orchestrator.submit`, pass them into `_TaskRunner(...)`:

```python
            workspace=self._workspace,
            enforcer=self._enforcer,
            scope_provider=self._scope_provider,
        )
```

- [ ] **Step 3c: Add the gate in `_execute_step`**

Insert the gate at the very top of `_execute_step`, immediately after the `invocation = ToolInvocation(...)` block and **before** the `if self.machine.state is TaskState.VERIFYING:` line:

```python
        # Scope gate — deny out-of-scope targets before any move toward EXECUTING.
        allowed_scope = await self._scope_provider()
        if not await self._scope_gate(step, invocation, allowed_scope):
            return False
```

Add the helper method to `_TaskRunner`:

```python
    async def _scope_gate(
        self, step: PlanStep, invocation: ToolInvocation, allowed_scope: ResourceScope
    ) -> bool:
        tool = self._registry.get(step.tool_name)
        try:
            parsed = tool.parse_arguments(invocation)
            self._enforcer.check(tool.requested_scope(parsed), allowed_scope)
        except ScopeViolation as exc:
            await self._audit_only(
                "scope.denied",
                {"step_id": step.id, "tool": step.tool_name,
                 "kind": exc.kind, "value": exc.value, "reason": exc.reason},
            )
            await self._fail(f"step '{step.title}' blocked by scope: {exc.reason}")
            return False
        except ValidationError as exc:
            await self._audit_only(
                "scope.denied",
                {"step_id": step.id, "tool": step.tool_name, "reason": f"invalid arguments: {exc}"},
            )
            await self._fail(f"step '{step.title}' has invalid arguments")
            return False
        return True
```

Thread `allowed_scope` into execution: change `_run_tool` to accept and forward it, and update its call site in the retry loop.

`_run_tool` signature + body:

```python
    async def _run_tool(
        self, invocation: ToolInvocation, allowed_scope: ResourceScope
    ) -> ToolResult:
        exec_task = asyncio.ensure_future(
            guarded_execute(self.machine, self._registry, invocation, allowed_scope)
        )
        ...  # rest unchanged
```

Its call site inside the `while True:` loop of `_execute_step`:

```python
            result = await self._run_tool(invocation, allowed_scope)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/core/test_scope_integration.py apps/daemon/tests/test_orchestrator.py -q`
Expected: PASS — the 2 new integration tests plus the full existing orchestrator suite (mocks request empty scope, so their gate always passes).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/core/orchestrator.py apps/daemon/tests/core/test_scope_integration.py
git commit -m "feat(core): orchestrator pre-EXECUTING scope gate; thread scope to executor" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Permissions API + app wiring

**Files:**
- Create: `apps/daemon/src/omnimac_daemon/api/permissions.py`
- Modify: `apps/daemon/src/omnimac_daemon/app.py`
- Test: `apps/daemon/tests/api/test_permissions_api.py`

**Interfaces:**
- Consumes: `PermissionStore` (Task 4), `AuditStore`, `ScopeEnforcer`, `PermissionGrant`, `PermissionKind`, `WorkspaceProfile`, `ResourceScope`.
- Produces: routes `GET /api/permissions`, `POST /api/permissions/grants`, `DELETE /api/permissions/grants/{id}`, `GET /api/workspaces`, `POST /api/workspaces`; `app.state.permissions`, `app.state.audit`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/api/test_permissions_api.py
from httpx import AsyncClient


async def _default_ws(client: AsyncClient) -> dict:
    return (await client.get("/api/permissions")).json()["workspaces"][0]


async def test_permissions_lists_seeded_default_workspace(client: AsyncClient) -> None:
    r = await client.get("/api/permissions")
    assert r.status_code == 200
    body = r.json()
    assert "workspaces" in body and "grants" in body
    assert len(body["workspaces"]) == 1


async def test_create_and_list_grant(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    r = await client.post(
        "/api/permissions/grants",
        json={"workspace_id": ws["id"], "kind": "domain", "value": "example.com"},
    )
    assert r.status_code == 200
    grants = (await client.get("/api/permissions")).json()["grants"]
    assert any(g["value"] == "example.com" for g in grants)


async def test_grant_rejects_extra_field(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    r = await client.post(
        "/api/permissions/grants",
        json={"workspace_id": ws["id"], "kind": "domain", "value": "x", "foo": 1},
    )
    assert r.status_code == 422


async def test_grant_rejects_unknown_kind(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    r = await client.post(
        "/api/permissions/grants",
        json={"workspace_id": ws["id"], "kind": "network", "value": "x"},
    )
    assert r.status_code == 422


async def test_revoke_grant(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    created = (
        await client.post(
            "/api/permissions/grants",
            json={"workspace_id": ws["id"], "kind": "app", "value": "Safari"},
        )
    ).json()
    r = await client.delete(f"/api/permissions/grants/{created['id']}")
    assert r.status_code == 200
    grants = (await client.get("/api/permissions")).json()["grants"]
    assert all(g["id"] != created["id"] for g in grants)


async def test_revoke_unknown_grant_404(client: AsyncClient) -> None:
    r = await client.delete("/api/permissions/grants/does-not-exist")
    assert r.status_code == 404


async def test_grant_emits_system_audit_event(client: AsyncClient) -> None:
    ws = await _default_ws(client)
    await client.post(
        "/api/permissions/grants",
        json={"workspace_id": ws["id"], "kind": "domain", "value": "audited.com"},
    )
    audit = (await client.get("/api/tasks/system/audit")).json()
    assert any(e["event_type"] == "permission.granted" for e in audit)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/api/test_permissions_api.py -q`
Expected: FAIL — 404s (routes not registered).

- [ ] **Step 3a: Write the router**

```python
# apps/daemon/src/omnimac_daemon/api/permissions.py
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from omnimac_daemon.audit.store import AuditStore
from omnimac_daemon.schemas import PermissionGrant, PermissionKind, WorkspaceProfile
from omnimac_daemon.storage.permissions import PermissionStore

router = APIRouter()

SYSTEM_TASK_ID = "system"


class GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    kind: PermissionKind
    value: str


class WorkspaceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    root_path: str
    trusted: bool = False
    approved_domains: list[str] = []
    approved_apps: list[str] = []


def _store(request: Request) -> PermissionStore:
    return cast(PermissionStore, request.app.state.permissions)


def _audit(request: Request) -> AuditStore:
    return cast(AuditStore, request.app.state.audit)


@router.get("/api/permissions")
async def get_permissions(request: Request) -> dict[str, Any]:
    store = _store(request)
    return {
        "workspaces": [w.model_dump(mode="json") for w in await store.list_workspaces()],
        "grants": [g.model_dump(mode="json") for g in await store.list_grants()],
    }


@router.post("/api/permissions/grants")
async def create_grant(body: GrantBody, request: Request) -> dict[str, Any]:
    grant = PermissionGrant(workspace_id=body.workspace_id, kind=body.kind, value=body.value)
    await _store(request).add_grant(grant)
    await _audit(request).append(SYSTEM_TASK_ID, "permission.granted", grant.model_dump(mode="json"))
    return grant.model_dump(mode="json")


@router.delete("/api/permissions/grants/{grant_id}")
async def revoke_grant(grant_id: str, request: Request) -> dict[str, Any]:
    if not await _store(request).revoke_grant(grant_id):
        raise HTTPException(status_code=404, detail="grant not found")
    await _audit(request).append(SYSTEM_TASK_ID, "permission.revoked", {"grant_id": grant_id})
    return {"revoked": grant_id}


@router.get("/api/workspaces")
async def list_workspaces(request: Request) -> list[dict[str, Any]]:
    return [w.model_dump(mode="json") for w in await _store(request).list_workspaces()]


@router.post("/api/workspaces")
async def upsert_workspace(body: WorkspaceBody, request: Request) -> dict[str, Any]:
    profile = WorkspaceProfile(
        **({"id": body.id} if body.id else {}),
        name=body.name,
        root_path=body.root_path,
        trusted=body.trusted,
        approved_domains=body.approved_domains,
        approved_apps=body.approved_apps,
    )
    await _store(request).upsert_workspace(profile)
    await _audit(request).append(SYSTEM_TASK_ID, "workspace.upserted", profile.model_dump(mode="json"))
    return profile.model_dump(mode="json")
```

- [ ] **Step 3b: Wire it in `app.py`**

Add imports:

```python
from omnimac_daemon.api import health, permissions, tasks, ws
from omnimac_daemon.core.scope import ScopeEnforcer
from omnimac_daemon.schemas import ResourceScope, WorkspaceProfile
from omnimac_daemon.storage.permissions import PermissionStore
```

Inside `lifespan`, replace the workspace/orchestrator construction block with:

```python
        permissions_store = PermissionStore(session_factory)
        existing = await permissions_store.list_workspaces()
        if existing:
            default_ws = existing[0]
        else:
            default_ws = WorkspaceProfile(
                name="default",
                root_path=cfg.trusted_workspaces[0] if cfg.trusted_workspaces else "",
                trusted=bool(cfg.trusted_workspaces),
            )
            await permissions_store.upsert_workspace(default_ws)
        app.state.permissions = permissions_store

        audit_store = AuditStore(session_factory)
        app.state.audit = audit_store

        async def scope_provider() -> ResourceScope:
            return await permissions_store.effective_scope(default_ws.id)

        app.state.orchestrator = Orchestrator(
            registry=build_registry(),
            policy=PolicyEngine(),
            approvals=ApprovalEngine(ttl_seconds=cfg.approval_ttl_seconds),
            verifier=VerificationEngine(),
            recovery=RecoveryController(
                max_retries_per_step=cfg.max_retries_per_step,
                max_retries_per_task=cfg.max_retries_per_task,
            ),
            audit=audit_store,
            planner=DeterministicMockPlanner(),
            publish=publish,
            workspace=default_ws,
            enforcer=ScopeEnforcer(),
            scope_provider=scope_provider,
        )
```

Register the router near the other `include_router` calls:

```python
    app.include_router(permissions.router)
```

(The previous inline `workspace = WorkspaceProfile(...)` and `audit=AuditStore(session_factory)` are removed — they're replaced above.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/api/test_permissions_api.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/api/permissions.py apps/daemon/src/omnimac_daemon/app.py \
        apps/daemon/tests/api/test_permissions_api.py
git commit -m "feat(api): permissions router; wire PermissionStore + scope provider into app" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Schema export, docs, ADR, full-suite gate

**Files:**
- Modify: `apps/daemon/src/omnimac_daemon/schemas/export.py`
- Modify: `docs/DECISIONS.md`, `docs/STATUS.md`, `docs/MILESTONES.md`
- Regenerate: `packages/shared-schemas/**` (via `make schemas`)

- [ ] **Step 1: Add PermissionGrant to the exported contracts**

In `apps/daemon/src/omnimac_daemon/schemas/export.py`, add to the `CONTRACTS` list:

```python
    schemas.PermissionGrant,
```

- [ ] **Step 2: Regenerate shared schemas**

Run: `make schemas`
Expected: writes `PermissionGrant.json` (and rewrites the set) under `packages/shared-schemas`.

- [ ] **Step 3: Write the ADR**

Append to `docs/DECISIONS.md`:

```markdown
## ADR-00N: Central ScopeEnforcer completes "executor enforces resource_scope"

**Status:** accepted (Phase 3, slice 1)

`ToolDefinition.requested_scope(args)` declares the concrete paths/domains/apps
an invocation will touch. A stateless `ScopeEnforcer` checks it against the
effective allowed scope resolved from `PermissionStore` — first at the
orchestrator pre-EXECUTING gate (fail fast, task FAILED, never enters
EXECUTING), then again in `registry.execute` as a backstop. This implements
the previously-unenforced "executor enforces resource_scope" clause of
TOOL_CONTRACTS §1.

**Alternatives rejected:** per-tool ad-hoc checks (un-auditable, easy to
forget); enforcement only in the executor (misses fail-fast before EXECUTING).
Grants are mutated only through the trusted `/api/permissions` endpoints, so
untrusted content can never widen scope.
```
(Replace `00N` with the next ADR number in the file.)

- [ ] **Step 4: Update STATUS and MILESTONES truthfully**

In `docs/STATUS.md`, under "Mocked / not yet implemented", note that scope enforcement + the permission store/API now exist while capabilities remain mocked; keep the "OmniMac cannot control the computer" statement. In `docs/MILESTONES.md` Phase 3, add a completed sub-line under the filesystem/permissions items:

```markdown
- [x] Scope enforcement (`ScopeEnforcer`, orchestrator gate + registry backstop) + persistent permission store & `/api/permissions` (slice 1; no real I/O yet)
```

- [ ] **Step 5: Run the full gate**

```bash
uv run --project apps/daemon pytest apps/daemon/tests -q
uv run --project apps/daemon ruff check apps/daemon
uv run --project apps/daemon ruff format --check apps/daemon
uv run --project apps/daemon mypy apps/daemon/src
make migrate   # applies 0001 + 0002 cleanly on a fresh DB
```
Expected: pytest all green (256 prior + new, no regressions); ruff clean; mypy no issues; alembic upgrades to head. (No desktop change this slice — vitest untouched.)

- [ ] **Step 6: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/schemas/export.py packages/shared-schemas docs/DECISIONS.md docs/STATUS.md docs/MILESTONES.md
git commit -m "docs: ADR + status for scope enforcement; export PermissionGrant schema" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (each spec §, mapped to a task):
- §3 components → Tasks 1–7 (paths, scope, store, api, base/registry, orchestrator, app).
- §4 data model → Task 3 (contract, tables, migration).
- §5 enforcement (declare, effective scope, check, primary gate, backstop) → Tasks 5 (hook+backstop), 4 (effective_scope), 2 (check), 6 (gate).
- §6 denylist → Task 1.
- §7 API → Task 7.
- §8 wiring → Task 7.
- §9 error handling & audit (`scope.denied`, `permission.granted/revoked`, `workspace.upserted`) → Tasks 6, 7.
- §10 tests → each task's test step + Task 8 full gate.
- §11 invariants + §12 ADR → Task 8.

**Placeholder scan:** No TBD/TODO in code steps; every step ships complete code and exact commands. `ADR-00N` / `00N` and the migration `Create Date` are the only fill-ins, each flagged inline with the rule for choosing the value.

**Type consistency:** `requested_scope(args) -> ResourceScope`, `ScopeEnforcer.check(requested, allowed) -> None`, `ScopeViolation.kind/value/reason`, `execute(invocation, allowed_scope=None)`, `guarded_execute(..., allowed_scope=None)`, `scope_provider() -> ResourceScope`, `effective_scope(workspace_id) -> ResourceScope`, `revoke_grant(id) -> bool` — names/signatures match across Tasks 2, 4, 5, 6, 7.
