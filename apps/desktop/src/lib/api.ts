/**
 * Typed HTTP client for the THOTH daemon. The desktop is a thin client:
 * every mutation here maps 1:1 to a daemon endpoint, and no business
 * logic lives on this side.
 */
import type { ApprovalRequest, Task } from "@thoth/shared-schemas";

import { getSessionToken } from "./auth";

export const DAEMON_URL =
  (import.meta.env.VITE_DAEMON_URL as string | undefined) ??
  "http://127.0.0.1:7710";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getSessionToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(`${DAEMON_URL}${path}`, { ...init, headers });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
  return (await resp.json()) as T;
}

export interface HealthResponse {
  status: string;
  version: string;
  db: string;
}

export interface Grant {
  id: string;
  workspace_id: string;
  kind: "path" | "domain" | "app";
  value: string;
}

export interface Workspace {
  id: string;
  name: string;
  root_path: string;
  trusted: boolean;
}

export interface PermissionsResponse {
  workspaces: Workspace[];
  grants: Grant[];
}

export interface SkillDef {
  id: string;
  name: string;
  description: string;
  workflow: string[];
  inputs: string[];
  enabled: boolean;
}

export interface SettingsResponse {
  version: string;
  planner: string;
  approval_ttl_seconds: number;
  max_retries_per_step: number;
  max_retries_per_task: number;
  trusted_workspaces: string[];
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  permissions: () => request<PermissionsResponse>("/api/permissions"),
  revokeGrant: (id: string) =>
    request<{ revoked: string }>(`/api/permissions/grants/${id}`, {
      method: "DELETE",
    }),
  skills: () => request<SkillDef[]>("/api/skills"),
  setSkillEnabled: (id: string, enabled: boolean) =>
    request<SkillDef>(`/api/skills/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    }),
  settings: () => request<SettingsResponse>("/api/settings"),
  createTask: (goal: string, source: "text" | "voice" = "text") =>
    request<Task>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ goal, source }),
    }),
  listTasks: () => request<Task[]>("/api/tasks"),
  getTask: (id: string) => request<Task>(`/api/tasks/${id}`),
  cancelTask: (id: string) =>
    request<Task>(`/api/tasks/${id}/cancel`, { method: "POST" }),
  pendingApprovals: () => request<ApprovalRequest[]>("/api/approvals/pending"),
  decideApproval: (
    id: string,
    approved: boolean,
    modifiedArguments?: Record<string, unknown>,
  ) =>
    request<ApprovalRequest>(`/api/approvals/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({
        approved,
        modified_arguments: modifiedArguments ?? null,
      }),
    }),
  taskAudit: (id: string) =>
    request<import("@thoth/shared-schemas").AuditEvent[]>(
      `/api/tasks/${id}/audit`,
    ),
};
