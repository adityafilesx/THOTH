"""Permission store — persistent workspaces and scope grants.

Mirrors AuditStore's async-session style. Resolves the effective allowed
ResourceScope (workspace roots/domains/apps + active grants) the scope
enforcer checks against. Only trusted, user-initiated API calls mutate it;
untrusted content has no path here (threats T1/T3)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from thoth_daemon.schemas import PermissionGrant, ResourceScope, WorkspaceProfile
from thoth_daemon.storage.models import PermissionGrantRow, WorkspaceRow


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
            kind=row.kind,
            value=row.value,
            granted_at=row.granted_at,
            revoked=row.revoked,
        )
