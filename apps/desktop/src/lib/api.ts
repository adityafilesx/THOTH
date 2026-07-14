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

export type RuntimeState =
  | "unloaded"
  | "loading"
  | "ready"
  | "busy"
  | "idle_cached"
  | "evicting"
  | "degraded"
  | "failed";

export interface RuntimeComponentStatus {
  display_name: string;
  state: RuntimeState;
  memory_estimate_bytes: number;
  integrity_verified: boolean | null;
  heavy: boolean;
  detail: string;
}

export interface LocalRuntimeSnapshot {
  components: Record<"planner" | "speech_recognition" | "text_to_speech", RuntimeComponentStatus>;
  memory_limit_bytes: number;
  estimated_loaded_bytes: number;
  battery_saver: boolean;
  offline: boolean;
  reflex_available: boolean;
}

export interface VoiceSessionSnapshot {
  session_id: string;
  mode: "hold" | "toggle";
  activity: "idle" | "listening" | "speaking" | "silence" | "finalising" | "complete" | "cancelled" | "failed";
  microphone_visible: boolean;
  local_processing: true;
  partial: { text: string; stable_text: string; sequence: number } | null;
  final: { text: string; confidence: number; language: string; duration_s: number } | null;
  editable_text: string | null;
  correction_expires_at: string | null;
  submitted: boolean;
}

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

export type AXPermissionStatus =
  | "not_determined"
  | "denied"
  | "granted"
  | "revoked"
  | "unavailable";

export interface AXPermissionState {
  status: AXPermissionStatus;
  checked_at: string;
  stale_after: string;
  detail: string;
}

export interface AXDiagnostics {
  current_task_id: string | null;
  current_step_id: string | null;
  current_tool: string | null;
  bundle_id: string | null;
  semantic_target: {
    identifier: string | null;
    role: string | null;
    semantic_alias: string | null;
  } | null;
  resolution_method: string | null;
  resolution_confidence: number | null;
  candidate_count: number | null;
  focus_policy: FocusPolicy | null;
  verification_evidence: string | null;
  permission_error: string | null;
  clarification_required: boolean;
  updated_at: string | null;
}

export interface AccessibilityStatus {
  permission: AXPermissionState;
  applications: ApplicationProfile[];
  diagnostics: AXDiagnostics;
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
  accessibility: () => request<AccessibilityStatus>("/api/accessibility"),
  openAccessibilitySettings: () =>
    request<{ opened: boolean; permission: AXPermissionState }>(
      "/api/accessibility/open-settings",
      {
        method: "POST",
        body: JSON.stringify({ user_requested: true }),
      },
    ),
  dialogue: (taskId: string) =>
    request<Record<string, unknown>>(`/api/dialogue/${taskId}`),
  resolveDialogue: (taskId: string, text: string) =>
    request<Record<string, unknown>>(`/api/dialogue/${taskId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  runtime: () => request<LocalRuntimeSnapshot>("/api/runtime"),
  startVoiceSession: (mode: "hold" | "toggle" = "hold") =>
    request<VoiceSessionSnapshot>("/api/voice/sessions", {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),
  appendVoiceAudio: (sessionId: string, audio: Blob) =>
    request<VoiceSessionSnapshot>(`/api/voice/sessions/${sessionId}/audio`, {
      method: "PUT",
      headers: { "Content-Type": audio.type || "application/octet-stream" },
      body: audio,
    }),
  voicePartial: (sessionId: string) =>
    request<VoiceSessionSnapshot>(`/api/voice/sessions/${sessionId}/partial`, {
      method: "POST",
    }),
  finaliseVoiceSession: (sessionId: string) =>
    request<VoiceSessionSnapshot>(`/api/voice/sessions/${sessionId}/finalise`, {
      method: "POST",
    }),
  editVoiceTranscript: (sessionId: string, text: string) =>
    request<VoiceSessionSnapshot>(`/api/voice/sessions/${sessionId}/transcript`, {
      method: "PATCH",
      body: JSON.stringify({ text }),
    }),
  submitVoiceSession: (sessionId: string) =>
    request<{ stopped: boolean; task: TaskPayload | null }>(
      `/api/voice/sessions/${sessionId}/submit`,
      { method: "POST" },
    ),
  cancelVoiceSession: (sessionId: string) =>
    request<VoiceSessionSnapshot>(`/api/voice/sessions/${sessionId}`, {
      method: "DELETE",
    }),
  interruptSpeech: () =>
    request<{ interrupted: boolean }>("/api/voice/interrupt", { method: "POST" }),
  globalStop: (reason: "global_button" | "escape" | "menu_bar") =>
    request<Record<string, unknown>>("/api/stop", {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  routeIntent: (text: string) =>
    request<{ tier: "reflex" | "skill" | "planner" | "clarify" }>(
      "/api/intent/route",
      { method: "POST", body: JSON.stringify({ text }) },
    ),
};
