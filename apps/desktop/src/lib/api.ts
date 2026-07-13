/**
 * Typed HTTP client for the THOTH daemon. The desktop is a thin client:
 * every mutation here maps 1:1 to a daemon endpoint, and no business
 * logic lives on this side.
 */
import type { ApprovalRequest, FocusPolicy, Task } from "@thoth/shared-schemas";

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

export interface SkillStepDef {
  title: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  declared_risk: string;
  verification_checks: unknown[];
}

export interface SkillDef {
  id: string;
  name: string;
  description: string;
  workflow: string[];
  inputs: string[];
  steps: SkillStepDef[];
  enabled: boolean;
}

export interface SettingsResponse {
  version: string;
  planner: string;
  approval_ttl_seconds: number;
  max_retries_per_step: number;
  max_retries_per_task: number;
  trusted_workspaces: string[];
  inference_provider: string;
  inference_model: string;
  network_isolation: boolean;
}

export type ResponseIntent =
  | "acknowledgement"
  | "plan_ready"
  | "approval_required"
  | "execution_progress"
  | "verified_completion"
  | "partial_completion"
  | "failed"
  | "policy_refusal"
  | "needs_clarification"
  | "interrupted"
  | "degraded_mode"
  | "resumable_task";

export type LocalRuntimeStatus =
  "unavailable" | "starting" | "ready" | "generating" | "degraded" | "failed";

export interface ForegroundContext {
  captured_at: string;
  reason: string;
  active_bundle_id: string | null;
  active_app_name: string | null;
  active_window_title: string | null;
  focused_ax_role: string | null;
  focused_ax_identifier: string | null;
  browser_domain: string | null;
  selected_file_paths: string[];
  workspace_id: string | null;
  previous_bundle_id: string | null;
  task_id: string | null;
}

export interface FocusRestorationResult {
  restored: boolean;
  verified: boolean;
  requires_user: boolean;
  cancelled: boolean;
  final_bundle_id: string | null;
  detail: string;
}

export interface TaskStages {
  proposed: boolean;
  approval: "not_required" | "required" | "pending" | "approved" | "denied";
  executed: boolean;
  verified: boolean;
}

export interface TaskPresentation {
  task_id: string;
  authoritative: true;
  response: {
    intent: ResponseIntent;
    used_model: boolean;
    display: { text: string };
    spoken: { text: string; max_chars: number };
  };
  display_response: string;
  spoken_response_preview: string;
  foreground: ForegroundContext | null;
  matched_workspace_id: string | null;
  planned_focus_policy: FocusPolicy | null;
  focus_result: FocusRestorationResult | null;
  runtime_status: LocalRuntimeStatus;
  dialogue_expires_at: string | null;
  stages: TaskStages;
}

export type TaskPayload = Task & { presentation?: TaskPresentation };

export interface ApplicationProfile {
  bundle_id: string;
  display_name: string;
  version: string;
  verified_capabilities: string[];
  experimental_capabilities: string[];
  forbidden_operations: string[];
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
    request<TaskPayload>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ goal, source }),
    }),
  listTasks: () => request<TaskPayload[]>("/api/tasks"),
  getTask: (id: string) => request<TaskPayload>(`/api/tasks/${id}`),
  cancelTask: (id: string) =>
    request<TaskPayload>(`/api/tasks/${id}/cancel`, { method: "POST" }),
  pendingApprovals: () => request<ApprovalRequest[]>("/api/approvals/pending"),
  decideApproval: (
    id: string,
    approved: boolean,
    modifiedArguments?: Record<string, unknown>,
  ) =>
    request<TaskPayload>(`/api/approvals/${id}/decision`, {
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
  operationalStatus: (id: string) =>
    request<TaskPresentation>(`/api/operational-status/${id}`),
  foreground: (reason = "user_requested", taskId?: string) => {
    const query = new URLSearchParams({ reason });
    if (taskId) query.set("task_id", taskId);
    return request<ForegroundContext>(`/api/foreground?${query.toString()}`);
  },
  applicationProfiles: () =>
    request<ApplicationProfile[]>("/api/application-profiles"),
  dialogue: (taskId: string) =>
    request<Record<string, unknown>>(`/api/dialogue/${taskId}`),
  resolveDialogue: (taskId: string, text: string) =>
    request<Record<string, unknown>>(`/api/dialogue/${taskId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
};
