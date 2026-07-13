/**
 * TypeScript mirror of the daemon's Pydantic contracts
 * (apps/daemon/src/thoth_daemon/schemas/). Keep in lockstep — the JSON
 * Schemas under ../schemas are generated from the same source via
 * `make schemas` and are the source of truth for shapes.
 */

export type TaskState =
  | "RECEIVED"
  | "UNDERSTANDING"
  | "PLANNING"
  | "RISK_REVIEW"
  | "WAITING_FOR_APPROVAL"
  | "EXECUTING"
  | "VERIFYING"
  | "RECOVERING"
  | "COMPLETED"
  | "FAILED"
  | "FAILED_REQUIRES_USER"
  | "CANCELLED";

export const TASK_STATES: TaskState[] = [
  "RECEIVED",
  "UNDERSTANDING",
  "PLANNING",
  "RISK_REVIEW",
  "WAITING_FOR_APPROVAL",
  "EXECUTING",
  "VERIFYING",
  "RECOVERING",
  "COMPLETED",
  "FAILED",
  "FAILED_REQUIRES_USER",
  "CANCELLED",
];

export type RiskLevel = "R0" | "R1" | "R2" | "R3";

export type TaskSource = "text" | "voice";

export type StepStatus =
  | "pending"
  | "running"
  | "verifying"
  | "succeeded"
  | "failed"
  | "skipped"
  | "cancelled";

export type VerifierKind =
  | "file_exists"
  | "file_content"
  | "process_running"
  | "port_listening"
  | "http_health"
  | "git_state"
  | "application_running"
  | "accessibility_value"
  | "browser_url"
  | "browser_element"
  | "exit_code"
  | "composite";

export interface VerificationCheck {
  kind: VerifierKind;
  params: Record<string, unknown>;
  description: string;
  require: "all" | "any";
  children: VerificationCheck[];
}

export interface PlanStep {
  id: string;
  correlation_id: string;
  index: number;
  title: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  declared_risk: RiskLevel;
  status: StepStatus;
  verification_checks: VerificationCheck[];
  verification_passed: boolean | null;
  verification_detail: string | null;
}

export interface ExecutionPlan {
  id: string;
  correlation_id: string;
  task_id: string;
  summary: string;
  steps: PlanStep[];
}

export interface Task {
  id: string;
  correlation_id: string;
  goal: string;
  source: TaskSource;
  state: TaskState;
  plan: ExecutionPlan | null;
  result_summary: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export type ApprovalStatus = "pending" | "approved" | "denied" | "expired";

export interface ApprovalRequest {
  id: string;
  correlation_id: string;
  task_id: string;
  invocation_id: string;
  step_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  risk: RiskLevel;
  reason: string;
  target: string;
  status: ApprovalStatus;
  created_at: string;
  expires_at: string;
}

export interface AuditEvent {
  event_id: string;
  correlation_id: string;
  task_id: string;
  seq: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
  /** Tamper-evident hash chain (slice 9). */
  prev_hash: string;
  hash: string;
}

/** Result of GET /api/tasks/{id}/audit/verify. */
export interface ChainManifest {
  task_id: string;
  valid: boolean;
  events: number;
  head_hash: string;
  first_invalid_seq: number | null;
  reason: string;
}

export type WsEventType =
  | "connection.established"
  | "task.created"
  | "task.state_changed"
  | "task.step_started"
  | "task.step_finished"
  | "approval.requested"
  | "approval.decided"
  | "audit.appended";

export interface WsEnvelope {
  type: WsEventType;
  ts: string;
  payload: Record<string, unknown>;
}
