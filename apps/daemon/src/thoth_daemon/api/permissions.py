from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from thoth_daemon.audit.store import AuditStore
from thoth_daemon.schemas import PermissionGrant, PermissionKind, WorkspaceProfile
from thoth_daemon.storage.permissions import PermissionStore

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
    await _audit(request).append(
        SYSTEM_TASK_ID, "permission.granted", grant.model_dump(mode="json")
    )
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
        name=body.name,
        root_path=body.root_path,
        trusted=body.trusted,
        approved_domains=body.approved_domains,
        approved_apps=body.approved_apps,
    )
    if body.id:
        profile.id = body.id
    await _store(request).upsert_workspace(profile)
    await _audit(request).append(
        SYSTEM_TASK_ID, "workspace.upserted", profile.model_dump(mode="json")
    )
    return profile.model_dump(mode="json")
